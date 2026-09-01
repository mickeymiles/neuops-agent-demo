# -*- coding: utf-8 -*-
"""抄送透传单元测试：初始询价 A 携带抄送观察者，智能体后续 B/D/E/G 都应带这些人。

不依赖真实邮箱/服务器：用 FakeMG 记录发出的邮件并断言 cc 头。
复刻 test_ont_e2e_mock.py 的驱动模式，仅额外在 A 上挂 cc_email_list。
"""
import os
import tempfile

os.environ.setdefault("ONT_DB_PATH", tempfile.mktemp(suffix=".db"))
os.environ["ONT_REQUESTERS"] = "eng@corp.com"
os.environ["ONT_MAIL_USERNAME"] = "b4@corp.com"
# 该用例专门验证 G 结算邮件的抄送透传，故显式开启结算闭环（运行时默认关闭，预留后续启用）
os.environ["ONT_SETTLEMENT_ENABLED"] = "1"

import pytest

import app.ontology as ont
ont.init()
from app.ontology import orbit, execution, store


ENG = "eng@corp.com"
B4 = "b4@corp.com"
S1 = "s1@x.com"   # 供应商A（最低价 1000）
S2 = "s2@x.com"   # 供应商B（1200）
AP = "ap@x.com"   # 审批人
SUPPLIERS = [{"name": "供A", "email": S1}, {"name": "供B", "email": S2}]
APPROVERS = [AP]

# 初始询价 A 的抄送观察者（真实场景：审批人 b5 + 两个外部观察者）
OBS = [AP, "watcher1@neusoft.com", "watcher2@qq.com"]


class FakeMG:
    def __init__(self):
        self.mailbox = []
        self.sent = []
        self.seen = []
        self._n = 0

    def read_inbox(self, since_timestamp=0, filter_sender_email_list=None):
        return {"mails": list(self.mailbox)}

    def send_mail(self, to, subject, body_text, cc=None, reply_to_mail_id=None,
                  reply_refs_chain=None, reply_all_from=None):
        self._n += 1
        mid = f"<S{self._n}@t>"
        self.sent.append({
            "to": list(to) if isinstance(to, (list, tuple)) else [to],
            "subject": subject,
            "body": body_text,
            "cc": list(cc) if isinstance(cc, (list, tuple)) else ([cc] if cc else []),
            "mid": mid,
            "reply_to": reply_to_mail_id,
        })
        return {"success": True, "message_id": mid}

    def mark_seen_by_message_id(self, mid):
        self.seen.append(mid)
        return True


def _mail(mid, frm, body, references="", subject="PRJ001 询价", cc=None):
    return {
        "message_id": mid,
        "from_email": frm,
        "to_email_list": [B4],
        "cc_email_list": cc or [],
        "in_reply_to": references,
        "references": references,
        "subject": subject,
        "mail_body_text": body,
        "body": body,
    }


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    from app.ontology import schema
    monkeypatch.setattr(schema, "ONT_DB_PATH", str(tmp_path / "cc.db"))
    ont.init()
    yield


@pytest.fixture()
def gov():
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    yield
    execution.set_governor(mode="off", exec_enabled=False)


@pytest.fixture()
def mg(monkeypatch):
    m = FakeMG()
    monkeypatch.setattr(orbit, "config", lambda: {"suppliers": SUPPLIERS, "approvers": APPROVERS})
    return m


def _run(mg):
    return orbit.run_full(mg, use_llm=False)


def _assert_cc(sent, label, *expect):
    expect = [e.lower() for e in expect]
    for s in sent:
        cc = [c.lower() for c in s["cc"]]
        missing = [e for e in expect if e not in cc]
        assert not missing, f"{label} 邮件未携带抄送观察者 {missing}：cc={s['cc']} subj={s['subject']}"


def _assert_to_only(sent, label, *only):
    """断言邮件主送(to)恰好为 only 列表，观察者/审批人等不得混入主送。"""
    only = [o.lower() for o in only]
    for s in sent:
        to = [t.lower() for t in s["to"]]
        assert to == only, f"{label} 主送应为 {only}，实际 {to}（观察者不应进主送）：subj={s['subject']} cc={s['cc']}"


def test_cc_propagated_b_to_g(mg, gov):
    """A 带抄送 → B/D/E/G 全部携带这些抄送观察者。"""
    # 阶段 A：工程师发起询价，抄送 OBS
    mg.mailbox = [_mail("<A@t>", ENG,
                        "项目编号: PRJ001\n项目名称: 服务器硬盘备件\n备件类型: 硬盘\n"
                        "品牌: Seagate\n型号: ST8000\n规格: 8TB SATA\n成色: 全新\n"
                        "数量: 2\n收货地址: 北京市海淀区科技路1号\n紧急程度: 3天\n询价",
                        cc=OBS)]
    _run(mg)  # → 发 B 询价函

    # 阶段 B：两供应商报价（其回复 C 的 cc 含观察者，模拟生产里 B 抄送观察者后供应商回复携带这些收件人）
    mg.mailbox += [
        _mail("<Q2@t>", S1, "单价 1000元 货期 3天 全新 数量 2", references="<A@t>", cc=OBS),
        _mail("<Q6@t>", S2, "单价 1200元 货期 5天 原装 数量 2", references="<A@t>", cc=OBS),
    ]
    _run(mg)  # → 发 D 审批汇总

    # 阶段 C：审批人确认采购
    mg.mailbox += [_mail("<AP@t>", AP, "确认采购", references="<A@t>")]
    _run(mg)  # → 发 E 订货

    # 阶段 D：选中供应商发运单
    mg.mailbox += [_mail("<SH@t>", S1, "运单 SF1234567890 已发出", references="<A@t>")]
    _run(mg)  # → F

    # 阶段 E：工程师发更换完成邮件
    mg.mailbox += [_mail("<CL@t>", ENG, "更换完成，请结算", references="<A@t>")]
    _run(mg)  # → 发 G 结算

    tasks = store.list_tasks()
    assert len(tasks) == 1, tasks
    assert tasks[0]["status"] == "CLOSED", tasks[0]

    # 收集各阶段发出的邮件（用主题精确区分 E=订货确认 / G=采购结束，避免主送被合并时误配）
    b_s1 = next((s for s in mg.sent if s["to"] == [S1] and "询价" in s["subject"]), None)
    b_s2 = next((s for s in mg.sent if s["to"] == [S2] and "询价" in s["subject"]), None)
    d = next((s for s in mg.sent if ENG in s["to"] and AP in s["cc"]), None)
    e = next((s for s in mg.sent if "订货确认" in s["subject"]), None)
    g = next((s for s in mg.sent if "采购结束" in s["subject"]), None)
    assert b_s1 and b_s2 and d and e and g, "B/D/E/G 未发出"

    # 核心断言：B（两封）、D、E、G 都携带 A 的全部抄送观察者
    _assert_cc([b_s1, b_s2], "B", *OBS)
    _assert_cc([d], "D", *OBS)
    _assert_cc([e], "E", *OBS)
    _assert_cc([g], "G", *OBS)

    # 回归：E（订货确认）与 G（采购结束）主送必须为供应商本人，观察者/审批人不得混入主送，
    # 否则观察者会出现在主送里（reply-all To 合并的历史缺陷）。
    _assert_to_only([e], "E", S1)
    _assert_to_only([g], "G", S1)
