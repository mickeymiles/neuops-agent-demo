# -*- coding: utf-8 -*-
"""本体轨认领去重/防漏/防丢单/防误认领 验证。

回答的核心设计问题：是否需要「XX 时刻前的邮件都已处理」这类时间水位来防重复？
不需要——防重由三层机制负责（见 ingest.fetch_new_inquiry_facts 文档）：
  ① o_email.email_message_id 唯一键（持久账本）
  ② IMAP \\Seen 认领握手
  ③ task_id = OT-{md5(message_id)}，同一封邮件恒等于同一 task_id
水位（o_scan_state）的用途是反的：扩大扫描下界以**防漏**（停机期间补扫）。

覆盖：
  - 重复扫描不重复建任务（三层去重）
  - 停机超窗后水位把下界前移（防漏）
  - 建任务失败 → pending/failed 保留 → 下轮重试成功（防丢单）
  - 重试不依赖 IMAP 窗口（正文已落库）
  - 发起人白名单 + 排除自身邮件（防误认领）
  - read_inbox 失败时水位不推进
"""
import os
import tempfile
import time

import pytest

os.environ.setdefault("ONT_DB_PATH", tempfile.mktemp(suffix=".db"))
import app.ontology as ont

ont.init()
from app.ontology import ingest, orbit, store, execution, schema


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "ONT_DB_PATH", str(tmp_path / "claim.db"))
    ont.init()
    yield


@pytest.fixture()
def gov():
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    yield
    execution.set_governor(mode="off", exec_enabled=False)


def _mail(mid="<A1@eng>", frm="eng@x.com", subject="【备件询价】PRJ-1 硬盘", extra=""):
    return {
        "message_id": mid, "subject": subject,
        "mail_body_text": ("项目编号：PRJ-1\n项目名称：N\n类型：硬盘\n品牌：Seagate\nPN：ST-1\n"
                           "规格：1T\n成色：全新\n数量：3\n收货地址：addr\n紧急程度：48h" + extra),
        "from_email": frm, "in_reply_to": "", "references": "",
        "to_email_list": ["agent@x.com"], "cc_email_list": [],
    }


class MG:
    """可控收件箱：记录 read_inbox 收到的 since_timestamp，便于断言扫描窗口。"""

    def __init__(self, mails=None, fail=False):
        self.mailbox = list(mails or [])
        self.since_calls = []
        self.seen = []
        self.sent = []
        self.fail = fail
        self._n = 0

    def read_inbox(self, since_timestamp=0, **kw):
        self.since_calls.append(since_timestamp)
        if self.fail:
            return {"success": False, "error": "IMAP down", "mails": []}
        return {"mails": list(self.mailbox)}

    def send_mail(self, to, subject, body_text, cc=None, **kw):
        self._n += 1
        mid = f"<S{self._n}@t>"
        self.sent.append({"to": to, "subject": subject, "mid": mid})
        return {"success": True, "message_id": mid}

    def mark_seen_by_message_id(self, mid):
        self.seen.append(mid)
        return True


# ── 防重：不需要时间水位，三层去重即可 ────────────────────────────
def test_repeat_scan_creates_task_once(gov):
    """同一封邮件反复扫描：只建一个任务，且 message_id 决定 task_id（三层去重）。"""
    mg = MG([_mail()])
    first = orbit.claim_inquiries(mg, mode="ontology")
    assert len(first) == 1
    tid = first[0]

    # 再扫 3 轮（模拟调度器每分钟跑一次），不应再建任务
    for _ in range(3):
        assert orbit.claim_inquiries(mg, mode="ontology") == []
    assert len(store.list_tasks()) == 1
    # task_id 由 message_id 派生 → 幂等
    assert tid == f"OT-{orbit._shake('<A1@eng>')}"
    # SEEN 握手只做一次（第二层）
    assert mg.seen == ["<A1@eng>"]


def test_claim_status_done_blocks_reprocess(gov):
    """第一层：o_email.claim_status='done' 后 try_claim_email 返回 False。"""
    mg = MG([_mail()])
    orbit.claim_inquiries(mg, mode="ontology")
    assert store.try_claim_email({"email_message_id": "<A1@eng>"}) is False
    assert store.list_unclaimed_emails() == []


# ── 防漏：水位把扫描下界前移 ──────────────────────────────────────
def test_watermark_extends_window_after_downtime():
    """停机 5 天后重启：水位应把下界拉回停机时刻，而不是只扫固定 48h。"""
    now = int(time.time())
    downtime_start = now - 5 * 86400  # 5 天前最后一次成功扫描
    store.set_scan_ts(downtime_start, ingest.SCAN_KEY)

    since = ingest.scan_window(hours=48, now_ts=now)
    # 固定窗口只能扫到 2 天前，水位必须把下界拉到 5 天前（含 1h 缓冲）
    assert since <= downtime_start - ingest._SCAN_OVERLAP + 1
    assert since < now - 48 * 3600, "水位未生效，停机期间邮件会漏单"


def test_watermark_never_narrows_window():
    """水位比固定窗口更新时，不得收窄窗口（防重不靠窗口，收窄只会带来漏单风险）。"""
    now = int(time.time())
    store.set_scan_ts(now - 60, ingest.SCAN_KEY)  # 1 分钟前刚扫过
    since = ingest.scan_window(hours=48, now_ts=now)
    assert since <= now - 48 * 3600, "窗口被水位收窄了"


def test_scan_ts_advances_only_on_success(gov):
    """read_inbox 失败时不推进水位，下轮才能从更早处补扫。"""
    mg_bad = MG(fail=True)
    ingest.fetch_new_inquiry_facts(mg_bad, hours=48)
    assert store.get_scan_ts(ingest.SCAN_KEY) == 0, "扫描失败却推进了水位 → 会漏单"

    mg_ok = MG([_mail()])
    ingest.fetch_new_inquiry_facts(mg_ok, hours=48)
    assert store.get_scan_ts(ingest.SCAN_KEY) > 0


# ── 防丢单：两阶段消费 + 单封失败不中断整批 ─────────────────────────
def test_task_creation_failure_retries_next_round(gov, monkeypatch):
    """建任务中途异常 → 邮件留 failed → 下轮重试成功建出任务（原实现会永久丢单）。"""
    mg = MG([_mail()])

    boom = {"n": 0}
    real_upsert = store.upsert_task

    def flaky(task):
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("模拟落库失败")
        return real_upsert(task)

    monkeypatch.setattr(store, "upsert_task", flaky)
    assert orbit.claim_inquiries(mg, mode="ontology") == []      # 第一轮失败
    assert store.list_tasks() == []
    pend = store.list_unclaimed_emails()
    assert len(pend) == 1 and pend[0]["claim_status"] == "failed"

    # 第二轮：重试成功
    monkeypatch.setattr(store, "upsert_task", real_upsert)
    got = orbit.claim_inquiries(mg, mode="ontology")
    assert len(got) == 1, "失败邮件未被重试 → 询价永久丢失"
    assert store.list_unclaimed_emails() == []


def test_retry_independent_of_imap_window(gov, monkeypatch):
    """重试不依赖 IMAP 窗口：即使收件箱已空（窗口滑过），pending 邮件仍能救回。"""
    mg = MG([_mail()])
    real_upsert = store.upsert_task
    monkeypatch.setattr(store, "upsert_task",
                        lambda t: (_ for _ in ()).throw(RuntimeError("fail")))
    orbit.claim_inquiries(mg, mode="ontology")
    assert len(store.list_unclaimed_emails()) == 1

    monkeypatch.setattr(store, "upsert_task", real_upsert)
    mg_empty = MG([])                    # 收件箱查不到了
    got = orbit.claim_inquiries(mg_empty, mode="ontology")
    assert len(got) == 1, "正文已落库，应能脱离 IMAP 重试"


def test_one_bad_mail_does_not_block_others(gov, monkeypatch):
    """单封邮件异常不得中断整批（原实现异常冒泡，后面的邮件全不处理）。"""
    mg = MG([_mail(mid="<BAD@eng>"), _mail(mid="<OK@eng>")])
    real_upsert = store.upsert_task

    def selective(task):
        if task.get("threat_msg_id") == "<BAD@eng>":
            raise RuntimeError("坏邮件")
        return real_upsert(task)

    monkeypatch.setattr(store, "upsert_task", selective)
    got = orbit.claim_inquiries(mg, mode="ontology")
    assert len(got) == 1, "坏邮件把后续邮件一起带崩了"
    assert store.get_task(got[0])["threat_msg_id"] == "<OK@eng>"
    # 坏的那封留 failed 现场供重试与排障
    bad = [e for e in store.list_unclaimed_emails() if e["email_message_id"] == "<BAD@eng>"]
    assert bad and bad[0]["claim_status"] == "failed" and "坏邮件" in (bad[0]["claim_error"] or "")


# ── 防误认领：白名单 + 排除自身 ───────────────────────────────────
def test_requester_whitelist_blocks_spam():
    """「采购」是极常见词，白名单必须能挡住非发起人来的邮件。"""
    spam = _mail(mid="<AD@ad>", frm="promo@spam.com",
                 subject="集中采购大促销，备件低至五折")
    assert ingest.is_inquiry(spam) is True                                  # 不设白名单会误认领
    assert ingest.is_inquiry(spam, allow_senders=["eng@x.com"]) is False    # 白名单挡住
    assert ingest.is_inquiry(_mail(), allow_senders=["eng@x.com"]) is True  # 正常发起人放行


def test_requester_whitelist_domain_form():
    """白名单支持 @域名 形式。"""
    m = _mail(frm="someone@corp.com")
    assert ingest.is_inquiry(m, allow_senders=["@corp.com"]) is True
    assert ingest.is_inquiry(m, allow_senders=["@other.com"]) is False


def test_self_sent_mail_not_claimed():
    """排除智能体自己发的邮件：模板 B 主题含「询价」且非 Re:，同域回投会自我认领建任务。"""
    mine = _mail(mid="<B1@agent>", frm="agent@x.com", subject="【询价】Seagate ST-1 x 3")
    assert ingest.is_inquiry(mine) is True                            # 未设 self_email 时会自我认领
    assert ingest.is_inquiry(mine, self_email="agent@x.com") is False  # 排除生效


def test_reply_mail_never_claimed():
    """回复邮件（有 in_reply_to 或 Re: 主题）不得被当作新询价。"""
    r1 = dict(_mail(), in_reply_to="<A1@eng>")
    r2 = _mail(subject="Re: 【备件询价】PRJ-1 硬盘")
    assert ingest.is_inquiry(r1) is False
    assert ingest.is_inquiry(r2) is False
