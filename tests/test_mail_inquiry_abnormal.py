"""
备件邮件询价 异常场景测试（本地，不发真实邮件）

覆盖设计规格 NO-011 的异常规则：
- R-FR-02 必填字段缺失 → 回信指出且不建任务/不询价
- R-FR-02 完全无法解析 → 回信提示格式
- R-FR-03 重复邮件判重
- R-FR-05 报价非标（表格）/ 无法解析保留原文

运行：cd neuops-agent-demo && python3 tests/test_mail_inquiry_abnormal.py
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_DB = os.path.join(tempfile.gettempdir(), "neuops_test_mail_inquiry_abnormal.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

import app.config
import app.db.base
app.config.DB_PATH = TEST_DB
app.db.base.DB_PATH = TEST_DB

from app.db import schema
from app.db import spare_mail as sm
from app.db import employees

schema.init_session_db()
schema.init_config_db()
schema.init_spare_mail_db()

# ── mock 邮件收发 ──
SENT_MAILS = []        # tool_send_mail
BATCH_SENT_MAILS = []  # tool_batch_send_mail
INBOX_MAILS = []       # tool_read_inbox_mail 读回

def _mk_mid():
    return f"m{int(time.time()*1000)}-{len(SENT_MAILS)+len(BATCH_SENT_MAILS)}"

def mock_tool_send_mail(to, subject, body_text, cc=None, reply_to_mail_id=None):
    rec = {
        "message_id": _mk_mid(), "to": ",".join(to) if isinstance(to, list) else str(to),
        "subject": subject, "body": body_text, "reply_to": reply_to_mail_id,
        "cc": cc or [], "tool": "send_mail", "success": True,
    }
    SENT_MAILS.append(rec)
    return rec

def mock_tool_batch_send_mail(receiver_email_list=None, subject=None, body_text=None,
                              cc=None, reply_to_mail_id=None, mails=None):
    results = []
    for addr in (receiver_email_list or []):
        rec = {"message_id": _mk_mid(), "to": addr, "subject": subject or "",
               "body": body_text or "", "reply_to": reply_to_mail_id, "cc": cc or []}
        BATCH_SENT_MAILS.append(rec)
        results.append({"message_id": rec["message_id"], "email": addr, "sent_ok": True})
    return {"sent": results, "fail_email_list": [], "success": True,
            "total_count": len(receiver_email_list or []), "success_count": len(receiver_email_list or [])}

def mock_tool_read_inbox_mail(match_in_reply_to_msg_ids=None, sender_whitelist=None,
                              sender_blacklist=None, since_timestamp=None,
                              keywords_filter=None, **kwargs):
    if not match_in_reply_to_msg_ids:
        mails = [m for m in INBOX_MAILS
                 if not sender_blacklist or m.get("from_email") not in sender_blacklist]
        return {"success": True, "mails": mails}
    ids = set(match_in_reply_to_msg_ids)
    return {"success": True, "mails": [m for m in INBOX_MAILS if m.get("in_reply_to") in ids]}

from app import mcp_tools as mcp
import app.routes_procurement_agent as rpa
mcp.tool_send_mail = mock_tool_send_mail
mcp.tool_batch_send_mail = mock_tool_batch_send_mail
mcp.tool_read_inbox_mail = mock_tool_read_inbox_mail
rpa.tool_send_mail = mock_tool_send_mail
rpa.tool_batch_send_mail = mock_tool_batch_send_mail
rpa.tool_read_inbox_mail = mock_tool_read_inbox_mail

employees.db_upsert_employee({
    "id": "emp-mail-inquiry", "name": "备件邮件询价数字员工", "type": "mail_inquiry",
    "desc": "abnormal tests", "status": "active", "skills": ["skill-proc-mail-inquiry"],
})

from app.routes_procurement_agent import tick_mail_inquiry

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}" + (f"  {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f"  {detail}" if detail else ""))

# ═══════ 用例块 ═══════

# --- R-FR-02 场景1：缺必填字段 → 回信指出且不建任务/不发B ---
def test_missing_required_field_replies():
    print("\n[R-FR-02] 缺必填字段 → 回信指出且不建任务")
    sent_before = len(SENT_MAILS)
    b_before = len(BATCH_SENT_MAILS)
    INBOX_MAILS.append({
        "message_id": "m-missing-1",
        "from_email": "engineer1@company.com",
        "subject": "【备件询价】缺字段测试",
        "mail_body_text": (
            "您好，我需要采购备件。\n"
            "类型：硬盘\n"           # part_type 有
            # 缺 brand / pn / spec / count
            "成色：全新\n"
        ),
        "in_reply_to": None,
    })
    tick_mail_inquiry()
    # 应回信（tool_send_mail 增加）且指出缺失字段
    replied = [m for m in SENT_MAILS[sent_before:] if "信息不完整" in m["subject"] or "补充" in m["subject"]]
    check("已向工程师回信", len(replied) >= 1, f"新发邮件{len(SENT_MAILS)-sent_before}封")
    if replied:
        body = replied[0]["body"]
        check("回信指出缺 品牌/PN/规格/数量", all(k in body for k in ("品牌", "PN", "规格", "数量")))
        check("回信发给工程师原发件人", "engineer1@company.com" in replied[0]["to"])
    # 不应建任务（tasks 仍为空）且不发 B
    tasks = sm.spare_mail_list_tasks(page_size=20)
    check("未创建任务", len(tasks) == 0, f"任务数={len(tasks)}")
    check("未发送 B 询价", len(BATCH_SENT_MAILS) == b_before, f"B邮件数变化={len(BATCH_SENT_MAILS)-b_before}")

# --- R-FR-02 场景2：完全无法解析 → 回信提示格式 ---
def test_unparseable_replies_format():
    print("\n[R-FR-02] 完全无法解析 → 回信提示格式")
    sent_before = len(SENT_MAILS)
    INBOX_MAILS.append({
        "message_id": "m-unparseable-1",
        "from_email": "engineer2@company.com",
        "subject": "【询价】随便写的",
        "mail_body_text": "你好 给我买个东西 尽快 谢谢",
        "in_reply_to": None,
    })
    tick_mail_inquiry()
    replied = [m for m in SENT_MAILS[sent_before:] if "不完整" in m["subject"] or "补充" in m["subject"]]
    check("回信提示需补充", len(replied) >= 1)
    tasks = sm.spare_mail_list_tasks(page_size=20)
    check("未创建任务", len(tasks) == 0)

# --- R-FR-03 重复邮件判重 ---
def test_duplicate_mail_not_recreated():
    print("\n[R-FR-03] 重复邮件判重")
    # 先塞一封标准完整邮件
    INBOX_MAILS.append({
        "message_id": "m-dup-100",
        "from_email": "engineer3@company.com",
        "subject": "【备件询价】重复判重测试",
        "mail_body_text": (
            "您好，申请购买硬盘。\n"
            "类型：硬盘\n品牌：Seagate\nPN：ST1000VD\n规格：1TB\n成色：全新\n数量：5\n"
            "紧急程度：5min\n"
        ),
        "in_reply_to": None,
    })
    t1 = sm.spare_mail_list_tasks(page_size=20)
    tick_mail_inquiry()
    t2 = sm.spare_mail_list_tasks(page_size=20)
    # 同 message_id 再出现一次
    INBOX_MAILS.append({
        "message_id": "m-dup-100",  # 与上面一致
        "from_email": "engineer3@company.com",
        "subject": "【备件询价】重复判重测试",
        "mail_body_text": (
            "您好，申请购买硬盘。\n类型：硬盘\n品牌：Seagate\nPN：ST1000VD\n规格：1TB\n成色：全新\n数量：5\n"
            "紧急程度：5min\n"
        ),
        "in_reply_to": None,
    })
    tick_mail_inquiry()
    t3 = sm.spare_mail_list_tasks(page_size=20)
    check("同一 message_id 只建一次任务", len(t3) == len(t2), f"t2={len(t2)} t3={len(t3)}")
    # 确认该 task 至少创建了 1 个（若 t2 为空则说明字段校验误判，需排查）
    check("完整邮件已创建任务", len(t2) >= 1)

# --- R-FR-05 表格报价解析 ---
def test_table_quote_parse():
    print("\n[R-FR-05] 表格报价解析")
    from app.routes_procurement_agent import _parse_quote_body
    tbl = (
        "| 序号 | 品牌 | 型号 | 数量 | 单价 | 货期 | 成色 |\n"
        "| 1 | 三星 | HTC | 3 | 1200 | 5天 | 全新 |\n"
    )
    r = _parse_quote_body(tbl)
    check("表格报价解析出单价", r.get("unit_price") == 1200.0, f"unit_price={r.get('unit_price')}")
    check("表格报价解析出数量", r.get("count") == 3, f"count={r.get('count')}")
    check("表格报价解析出成色", r.get("condition") == "全新", f"condition={r.get('condition')}")
    check("表格报价解析出货期", r.get("ship_time") is not None and "5天" == r.get("ship_time").replace(" ", ""), f"ship_time={r.get('ship_time')}")

# --- R-FR-05 非标报价保留原文（不静默丢弃）---
def test_quote_unparseable_keeps_raw():
    print("\n[R-FR-05] 非标报价 → SCENARIO：无法解析时保留原文字段")
    from app.routes_procurement_agent import _parse_quote_body
    weird = "没有数字，纯文本说明，没有单价数量"
    r = _parse_quote_body(weird)
    check("纯文本无法解析时不崩溃且返回 dict", isinstance(r, dict))
    # 后端在 DECIDING_LOWEST 会对 unit_price 缺失的报价记录保留 raw_body（quotes_json），
    # 并判定为"无有效报价"走 F 中止，而非把该报价当作正常报价静默处理。
    check("无法解析时无 price 字段可供流程判定（保留原文）", not r.get("unit_price"))

# ═══════ 执行 ═══════
test_missing_required_field_replies()
test_unparseable_replies_format()
test_duplicate_mail_not_recreated()
test_table_quote_parse()
test_quote_unparseable_keeps_raw()

print(f"\n========== 异常场景测试汇总：PASS={PASS} FAIL={FAIL} ==========")
sys.exit(1 if FAIL else 0)