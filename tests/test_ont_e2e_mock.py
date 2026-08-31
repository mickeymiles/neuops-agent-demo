# -*- coding: utf-8 -*-
"""emp-009 本轨 B→D→E→F→G 全链路脱机集成测试（mock mailbox，不需真实口令）。

不依赖任何真实 SMTP/IMAP：FakeMG 记录发出的邮件、按阶段注入回复，
多轮 drive 推进状态机，断言每个阶段动作与最终 G 结算触发且发对对象。

这是 ont_smoke_real.py 的脱机等价物——smoke 需 4 个真实邮箱授权码，
本测试用假 gateway 证明「逻辑无死链、结算 G 真实会发」，填补 smoke 只验证到 F 的盲区。
"""
import os
import tempfile

os.environ.setdefault("ONT_DB_PATH", tempfile.mktemp(suffix=".db"))
os.environ["ONT_REQUESTERS"] = "eng@corp.com"
os.environ["ONT_MAIL_USERNAME"] = "b4@corp.com"

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


class FakeMG:
    """假邮箱网关：记录发出的邮件，按阶段返回注入的收件。"""
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


def _mail(mid, frm, body, references="", subject="PRJ001 询价"):
    return {
        "message_id": mid,
        "from_email": frm,
        "to_email_list": [B4],
        "cc_email_list": [],
        "in_reply_to": references,
        "references": references,
        "subject": subject,
        "mail_body_text": body,
        "body": body,
    }


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    from app.ontology import schema
    monkeypatch.setattr(schema, "ONT_DB_PATH", str(tmp_path / "e2e.db"))
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


def test_e2e_b_to_g(mg, gov):
    """全链路：b1询价 → b4发B询价函 → b2/b6报价 → b4发D审批 → b5确认 →
    b4发E订货 → 供应商发运单 → b4登记F → b1发更换完成 → b4发G结算。"""
    # 阶段 A：工程师发起询价
    mg.mailbox = [_mail("<A@t>", ENG,
                        "项目编号: PRJ001\n项目名称: 服务器硬盘备件\n备件类型: 硬盘\n"
                        "品牌: Seagate\n型号: ST8000\n规格: 8TB SATA\n成色: 全新\n"
                        "数量: 2\n收货地址: 北京市海淀区科技路1号\n紧急程度: 3天\n询价")]
    _run(mg)  # → 发 B 询价函

    # 阶段 B：两供应商报价
    mg.mailbox += [
        _mail("<Q2@t>", S1, "单价 1000元 货期 3天 全新 数量 2", references="<A@t>"),
        _mail("<Q6@t>", S2, "单价 1200元 货期 5天 原装 数量 2", references="<A@t>"),
    ]
    _run(mg)  # → 发 D 审批汇总

    # 阶段 C：审批人确认采购（沿用最低价 s1）
    mg.mailbox += [_mail("<AP@t>", AP, "确认采购", references="<A@t>")]
    _run(mg)  # → 发 E 订货

    # 阶段 D：选中供应商发运单
    mg.mailbox += [_mail("<SH@t>", S1, "运单 SF1234567890 已发出", references="<A@t>")]
    _run(mg)  # → receiveTrackingNumber（F）

    # 阶段 E：工程师发更换完成邮件
    mg.mailbox += [_mail("<CL@t>", ENG, "更换完成，请结算", references="<A@t>")]
    _run(mg)  # → 发 G 结算

    # 最终任务应当闭环
    tasks = store.list_tasks()
    assert len(tasks) == 1, tasks
    t = tasks[0]
    assert t["status"] == "CLOSED", t
    assert t["external_status"] == "R_SETTLE", t
    assert t["internal_status"] == "R_CLOSED", t

    # 至少发出 B/D/E/G 四封业务邮件
    assert len(mg.sent) >= 4, mg.sent

    # B 询价函：逐供应商各发一封（to 分别为 s1 / s2）
    b1 = next((s for s in mg.sent if s["to"] == [S1]), None)
    b2 = next((s for s in mg.sent if s["to"] == [S2]), None)
    assert b1 is not None and b2 is not None, mg.sent

    # D 审批汇总：发给工程师、抄送审批人
    d = next((s for s in mg.sent if ENG in s["to"] and AP in s["cc"]), None)
    assert d is not None, mg.sent

    # E 订货：发给选中（最低价）供应商、抄送工程师+审批人
    e = next((s for s in mg.sent if s["to"] == [S1] and ENG in s["cc"] and AP in s["cc"]), None)
    assert e is not None, mg.sent

    # G 结算：最后一封，发给选中供应商、抄送工程师+审批人
    g = mg.sent[-1]
    assert g["to"] == [S1], g
    assert ENG in g["cc"] and AP in g["cc"], g


def test_enabled_gate_false_sends_no_mail(mg, gov, monkeypatch):
    """emp-009 禁用时 run_full 不应发出任何业务邮件（enabled 开关真实生效）。"""
    monkeypatch.setattr(execution, "_employee_managed", lambda: False)

    mg.mailbox = [_mail("<A@t>", ENG, "项目编号 PRJ001 询价 硬盘")]
    _run(mg)
    mg.mailbox += [
        _mail("<Q2@t>", S1, "单价 1000元", references="<A@t>"),
        _mail("<Q6@t>", S2, "单价 1200元", references="<A@t>"),
        _mail("<AP@t>", AP, "确认采购", references="<A@t>"),
    ]
    _run(mg)

    # 禁用时不应发出任何业务邮件
    assert mg.sent == [], mg.sent
    # 但询价邮件仍会被认领建任务（claim 不依赖 needs_exec）
    assert len(store.list_tasks()) == 1
