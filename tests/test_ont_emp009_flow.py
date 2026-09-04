# -*- coding: utf-8 -*-
"""NO-012 本体轨全流程自走测试（用 FakeMG，不触真实 SMTP）。
覆盖 SEEN 认领→发询价B→收报价→审批D→订货E→运单→工程师确认闭环。
"""
import os
import tempfile
import pytest

os.environ["ONT_DB_PATH"] = tempfile.mktemp(suffix=".db")
# 该用例覆盖到工程师确认闭环（G 结算），显式开启结算闭环（运行时默认关闭，预留后续启用）
os.environ["ONT_SETTLEMENT_ENABLED"] = "1"
import app.ontology as ont
ont.init()
import app.ontology.orbit as orbit
from app.ontology import store, execution


@pytest.fixture(autouse=True)
def _fresh_ont_db(tmp_path, monkeypatch):
    """每个用例独立本体库，避免跨用例残留任务/状态互相污染。"""
    dbp = str(tmp_path / "ont-test.db")
    from app.ontology import schema
    monkeypatch.setattr(schema, "ONT_DB_PATH", dbp)
    ont.init()
    yield


class FakeMG:
    def __init__(self, inquiry_mail):
        self.mailbox = [inquiry_mail]
        self.sent = []
        self.seen = []
        self._n = 0

    def read_inbox(self, since_timestamp=0, filter_sender_email_list=None):
        return {"mails": list(self.mailbox)}

    def send_mail(self, to, subject, body_text, cc=None, reply_to_mail_id=None,
                  reply_refs_chain=None, reply_all_from=None):
        self._n += 1
        mid = f"<SELF{self._n}@test>"
        self.sent.append({"to": to, "subject": subject, "cc": cc, "message_id": mid,
                          "reply_to": reply_to_mail_id, "refs": reply_refs_chain,
                          "body_text": body_text})
        return {"tool": "send_mail", "success": True, "message_id": mid}

    def mark_seen_by_message_id(self, msg_id):
        self.seen.append(msg_id)
        return True


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setattr(orbit, "config", lambda: {
        "suppliers": [{"name": "供A", "email": "s1@x.com"}, {"name": "供B", "email": "s2@x.com"}],
        "approvers": ["approve@x.com"], "pms": ["pm@corp.com"]})
    inquiry = {
        "message_id": "<A1@eng>", "subject": "【备件询价】PRJ-1 硬盘",
        # 追加「无特殊要求，最低价中标」→ 走自动轨（收集后直送审批 D），
        # 本文件验证的是自动轨的建任务/发信/回信编排链路。
        "mail_body_text": ("项目编号：PRJ-1\n项目名称：N\n类型：硬盘\n品牌：Seagate\nPN：ST-1\n"
                           "规格：1T\n成色：全新\n数量：3\n收货地址：addr\n紧急程度：5min\n"
                           "无特殊要求，最低价中标"),
        "from_email": "eng@x.com", "in_reply_to": "", "references": "",
    }
    mg = FakeMG(inquiry)
    return mg


def _meta_update(task, **kw):
    meta = dict(task.get("spare_info") or {})
    meta.update(kw)
    store.upsert_task({**task, "spare_info": meta})


def test_full_flow(fake):
    mg = fake
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    try:
        # 1. 认领工程师询价 → 建 O_Task + SEEN
        claimed = orbit.claim_inquiries(mg, "ontology", 1.0)
        assert claimed, "应认领新询价"
        tid = claimed[0]
        assert tid in mg.seen or len(claimed) == 1
        assert store.get_task(tid)["mode"] == "ontology"

        # 2. 驱动 → 发询价B（模板B，主题以【询价】开头）
        orbit.drive("ontology", use_llm=False, mg=mg)
        b_sent = [s for s in mg.sent if s["subject"].startswith("【询价】")]
        assert b_sent, "应收发询价B"
        assert len(b_sent) == 2
        # 临期提醒（新特性）：5min 截止属窗口内且仍有供应商未报价 → 主动催报价
        remind = [s for s in mg.sent if "距报价截止" in s["subject"]]
        assert remind, "截止前窗口应触发临期催报价提醒"

        # 3. 两家供应商报价 → 驱动 → 发审批D（模板D）
        task = store.get_task(tid)
        _meta_update(task, quotes=[
            {"email": "s1@x.com", "unit_price": "1000"},
            {"email": "s2@x.com", "unit_price": "800"},
        ], deadline_passed=True)
        orbit.drive("ontology", use_llm=False, mg=mg)
        d_sent = [s for s in mg.sent if "询价汇总" in s["subject"]]
        assert d_sent, "应发审批汇总D"

        # 4. 审批选定(最低价 s2 → 已由 submitApproval 置 internal=R_APPROVAL) → 驱动 → 发订货E（模板E）
        task = store.get_task(tid)
        _meta_update(task, target_supplier="s2@x.com")
        orbit.drive("ontology", use_llm=False, mg=mg)
        e_sent = [s for s in mg.sent if "订货确认" in s["subject"]]
        assert e_sent, "应发订货E"

        # 5. 供应商回运单 → 驱动 → 登记单号
        task = store.get_task(tid)
        _meta_update(task, tracking_no="SF123456")
        orbit.drive("ontology", use_llm=False, mg=mg)
        assert store.get_task(tid)["external_status"] == "R_WAIT_SHIPPING"

        # 6. 工程师确认完成 → 驱动 → 闭环 R_SETTLE
        task = store.get_task(tid)
        _meta_update(task, engineer_close="测试完毕，备件更换完成")
        orbit.drive("ontology", use_llm=False, mg=mg)
        fin = store.get_task(tid)
        assert fin["status"] == "CLOSED"
        assert fin["external_status"] in ("R_SETTLE",)
    finally:
        execution.set_governor(mode="off", exec_enabled=False)


def test_governor_off_no_side_effect(fake):
    execution.set_governor(mode="off", exec_enabled=False)
    try:
        orbit.claim_inquiries(fake, "off", 0.0)  # off 不认领
        assert len(fake.seen) == 0
        assert len(fake.sent) == 0
    finally:
        pass


ADDR_ENG = "eng@x.com"
ADDR_APPROVER = "approve@x.com"
ADDR_SUP1 = "s1@x.com"
ADDR_SUP2 = "s2@x.com"


@pytest.fixture()
def fake_thread(monkeypatch):
    """经真实入向回复编排（process_replies）驱动全流程的 FakeMG。"""
    monkeypatch.setattr(orbit, "config", lambda: {
        "suppliers": [{"name": "供A", "email": ADDR_SUP1}, {"name": "供B", "email": ADDR_SUP2}],
        "approvers": [ADDR_APPROVER], "pms": ["pm@corp.com"]})
    class MG(FakeMG):
        def __init__(self):
            mail = {"message_id": "<A-ENG@test>", "subject": "【备件询价】PRJ-G 硬盘",
                    # 自动轨：声明「无特殊要求，最低价中标」→ 收集后直送审批 D
                    "mail_body_text": ("项目编号：PRJ-G\n项目名称：二期\n类型：硬盘\n品牌：Seagate\nPN：ST-G\n"
                                       "规格：2T\n成色：全新\n数量：5\n收货地址：B4\n紧急程度：5min\n"
                                       "无特殊要求，最低价中标"),
                    "from_email": ADDR_ENG, "in_reply_to": "", "references": ""}
            super().__init__(mail)

        def reply(self, mid, sender, body, subject="Re: X"):
            self._n += 1
            rmid = f"<R{self._n}@{sender.split('@')[0]}>"
            self.mailbox.append({"message_id": rmid, "subject": subject, "mail_body_text": body,
                                 "from_email": sender, "in_reply_to": mid, "references": mid})
            return rmid
    return MG()


def test_inbound_reply_orchestration(fake_thread):
    """SEEN 认领 → 发B → 供应商入向报价 → 发D → 审批人入向确认 → 发E → 供应商入向运单 → 工程师入向完成 → 闭环。"""
    mg = fake_thread
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    try:
        # 1 认领工程师询价，SEEN 握手指标已记
        claimed = orbit.claim_inquiries(mg, "ontology", 1.0)
        assert claimed and mg.seen
        tid = claimed[0]
        task = store.get_task(tid)
        b_mid_1, b_mid_2 = None, None
        # 2 收齐两家供应商报价（各自回复 B）：入向回复归集
        orbit.drive("ontology", use_llm=False, mg=mg)
        task = store.get_task(tid)
        b_mids = (task.get("spare_info") or {}).get("b_msg_ids") or []
        assert b_mids, "B询价已发应登记 b_msg_ids"
        for i, supmail in enumerate((ADDR_SUP1, ADDR_SUP2)):
            mid_ref = b_mids[i % len(b_mids)]
            mg.reply(mid_ref, supmail, f"单价：{1000 - i * 200}\n货期：7天\n成色：全新")
        updates = orbit.process_replies(mg)
        kinds = {u["kind"] for u in updates}
        assert "quote" in kinds, f"应归集到供应商报价, 得到 {kinds}"
        # 3 收集结束 → 发 D 汇总审批（模板D）
        orbit.drive("ontology", use_llm=False, mg=mg)
        assert [s for s in mg.sent if "询价汇总" in s["subject"]], "应收发审批D"
        task = store.get_task(tid)
        d_mid = (task.get("spare_info") or {}).get("d_msg_id")
        assert d_mid, "应登记 d_msg_id"
        # D 内部流：应在工程师询价(A)线程上回复，并携带工程师原始采购申请原文
        d_sent = [s for s in mg.sent if "询价汇总" in s["subject"]]
        assert d_sent[0]["reply_to"] == (task.get("spare_info") or {}).get("inquiry_mid"), "D 应回复工程师询价线程"
        assert "【引用】" in d_sent[0]["body_text"], "D 应携带工程师原始采购申请原文"
        # 未审批前不应下达订货 E
        orbit.drive("ontology", use_llm=False, mg=mg)
        assert not [s for s in mg.sent if "订货确认" in s["subject"]], "审批前不得发订货E"
        # 4 审批人 b5 在 D 上入向确认 → 选最低价下单 E（模板E）
        mg.reply(d_mid, ADDR_APPROVER, "最低报价确认，同意采购")
        up2 = orbit.process_replies(mg)
        assert any(u["kind"] == "approval" for u in up2), "应归集审批人确认"
        orbit.drive("ontology", use_llm=False, mg=mg)
        e_sent = [s for s in mg.sent if "订货确认" in s["subject"]]
        assert e_sent, "审批确认后应发订货E"
        # E 订货必须在选中供应商的报价(C/供应商回复)线程上回复，并携带其报价原文
        task = store.get_task(tid)
        q_s2 = next(q for q in (task.get("spare_info") or {}).get("quotes", []) if q.get("email") == ADDR_SUP2)
        assert e_sent[0]["reply_to"] == q_s2["msg_id"], f"E 应回复供应商报价线程: {e_sent[0]['reply_to']}"
        assert "【引用】" in e_sent[0]["body_text"], "E 应携带供应商报价原文"
        e_mid = (task.get("spare_info") or {}).get("e_msg_id")
        assert e_mid
        # 5 供应商在 E 上入向回运单 → 登记单号
        mg.reply(e_mid, ADDR_SUP2, "快递单号 SF123456 已发出")
        orbit.process_replies(mg)
        orbit.drive("ontology", use_llm=False, mg=mg)
        task = store.get_task(tid)
        assert task["external_status"] == "R_WAIT_SHIPPING", task["external_status"]
        # 6 工程师在 E 线程确认完成 → 闭环 G 结算
        mg.reply(e_mid, ADDR_ENG, "测试完毕，备件更换完成，同意结算")
        parity = orbit.process_replies(mg)
        # 最后驱动：engineer_close 已写入，驱动发 G 结算
        orbit.drive("ontology", use_llm=False, mg=mg)
        fin = store.get_task(tid)
        assert fin["status"] == "CLOSED", fin["status"]
        assert fin["external_status"] in ("R_SETTLE",), fin["external_status"]
        # G 结算（模板G）：应在选中供应商报价(C)线程上回复，携带报价+运单原文
        g_sent = [s for s in mg.sent if "采购结束" in s["subject"]]
        assert g_sent, "应收发结算G"
        assert g_sent[0]["reply_to"] == q_s2["msg_id"], f"G 应回复供应商报价线程: {g_sent[0]['reply_to']}"
        assert "【引用】" in g_sent[0]["body_text"] and "SF123456" in g_sent[0]["body_text"], "G 应携带报价+运单原文"
    finally:
        execution.set_governor(mode="off", exec_enabled=False)