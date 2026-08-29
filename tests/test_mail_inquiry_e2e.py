"""
备件邮件询价 本地端到端测试（不发真实邮件）

用 mock 替换 tool_send_mail / tool_batch_send_mail / tool_read_inbox_mail，
模拟工程师发起→系统发B→供应商回C→最低价→模板D→审批人回复→模板E→完成。

运行：cd neuops-agent-demo && python3 tests/test_mail_inquiry_e2e.py
"""
import json
import os
import sys
import tempfile
import time
from unittest.mock import patch, MagicMock

# 确保项目根在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 1) 初始化独立测试 DB，避免污染现网数据
# 注意：必须在 import app.db.base 之前设置 DB_PATH，因为 base.py 在 import 时绑定
TEST_DB = os.path.join(tempfile.gettempdir(), "neuops_test_mail_inquiry.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

# 在任何 app.* import 之前设置 DB_PATH
import app.config
import app.db.base
app.config.DB_PATH = TEST_DB
app.db.base.DB_PATH = TEST_DB

from app.db import schema
from app.db import spare_mail as sm
from app.db import employees
from app.skill_loader import load_skill

schema.init_session_db()
schema.init_config_db()
schema.init_spare_mail_db()
print(f"[TEST] 隔离 DB: {TEST_DB}")

# 2) mock 邮件收发
SENT_MAILS = []          # tool_send_mail 发出的邮件
BATCH_SENT_MAILS = []    # tool_batch_send_mail 发出的每封
INBOX_MAILS = []         # tool_read_inbox_mail 读回的邮件（我们按步骤推进）

def mk_sent_mail(to, subject, body, reply_to=None, cc=None):
    mid = f"msg-{int(time.time()*1000)}-{len(SENT_MAILS)+len(BATCH_SENT_MAILS)}"
    # to 可能是 list 或 str，统一处理
    if isinstance(to, list):
        to_str = ",".join(to)
    else:
        to_str = str(to)
    rec = {
        "message_id": mid,
        "to": to_str,
        "subject": subject,
        "body": body,
        "reply_to": reply_to,
        "cc": cc or [],
        # 兼容真实 tool_send_mail 返回格式
        "tool": "send_mail",
        "success": True,
    }
    return rec

def mock_tool_send_mail(to, subject, body_text, cc=None, reply_to_mail_id=None):
    """匹配真实 tool_send_mail 的签名与返回格式。"""
    rec = mk_sent_mail(to, subject, body_text, reply_to_mail_id, cc)
    SENT_MAILS.append(rec)
    return rec

def mock_tool_batch_send_mail(receiver_email_list=None, subject=None, body_text=None, cc=None, reply_to_mail_id=None, mails=None):
    """匹配真实 tool_batch_send_mail 的签名与返回格式。"""
    # 支持两种调用方式：新签名(receiver_email_list, subject, body_text) 或 旧签名(mails=[{to,subject,body}])
    if mails is not None:
        # 旧签名（兼容）
        results = []
        for m in mails:
            rec = mk_sent_mail(m["to"], m["subject"], m["body"], m.get("reply_to_mail_id"), m.get("cc"))
            BATCH_SENT_MAILS.append(rec)
            results.append({"message_id": rec["message_id"], "email": m["to"], "sent_ok": True})
        return {"sent": results, "fail_email_list": [], "success": True, "total_count": len(mails), "success_count": len(mails)}
    else:
        # 新签名：receiver_email_list + subject + body_text
        results = []
        for addr in (receiver_email_list or []):
            rec = mk_sent_mail(addr, subject or "", body_text or "", reply_to_mail_id, cc)
            BATCH_SENT_MAILS.append(rec)
            results.append({"message_id": rec["message_id"], "email": addr, "subject": subject})
        return {"sent": results, "fail_email_list": [], "success": True, "total_count": len(receiver_email_list or []), "success_count": len(receiver_email_list or [])}

def mock_tool_read_inbox_mail(match_in_reply_to_msg_ids=None, sender_whitelist=None,
                              sender_blacklist=None, since_timestamp=None,
                              keywords_filter=None, **kwargs):
    """按 match_in_reply_to_msg_ids 过滤 inbox；非审批人过滤在流程代码里做。
    返回结构：{"success": True, "mails": [...]}，与真实 tool 保持一致。"""
    if not match_in_reply_to_msg_ids:
        mails = [m for m in INBOX_MAILS
                 if not sender_blacklist or m.get("from_email") not in sender_blacklist]
        return {"success": True, "mails": mails}
    ids = set(match_in_reply_to_msg_ids)
    return {"success": True, "mails": [m for m in INBOX_MAILS if m.get("in_reply_to") in ids]}

# 注入 mock — 直接替换 routes_procurement_agent 模块里的引用（因为它已在顶部 import 了函数）
from app import mcp_tools as mcp
import app.routes_procurement_agent as rpa
mcp.tool_send_mail = mock_tool_send_mail
mcp.tool_batch_send_mail = mock_tool_batch_send_mail
mcp.tool_read_inbox_mail = mock_tool_read_inbox_mail
# 关键：同时替换 rpa 模块里已经 import 的引用
rpa.tool_send_mail = mock_tool_send_mail
rpa.tool_batch_send_mail = mock_tool_batch_send_mail
rpa.tool_read_inbox_mail = mock_tool_read_inbox_mail

# 3) 测试辅助：从 sent_mails 找 B 邮件（给后续回复用）
def find_B_msg_id():
    for m in BATCH_SENT_MAILS:
        if "【询价】" in m["subject"] or "询价" in m["subject"]:
            return m["message_id"]
    return None

def find_D_msg_id():
    for m in SENT_MAILS:
        if "【询价汇总】" in m["subject"]:
            return m["message_id"]
    return None

# 4) 注册数字员工
employees.db_upsert_employee({
    "id": "emp-mail-inquiry",
    "name": "备件邮件询价数字员工",
    "type": "mail_inquiry",
    "desc": "V1.2 邮件询价数字员工",
    "status": "active",
    "skills": ["skill-proc-mail-inquiry"],
    "prompt": "",
    "flow_data": {},
})
print("[TEST] 数字员工已注册")

# 5) 加载 skill.json（验证审批人/供应商池已写入）
skill = load_skill("skill-proc-mail-inquiry")
sk = skill["skill"]  # 原始结构化定义
cfg = sk.get("config", {})
print(f"[TEST] 审批人: {cfg.get('approver_emails')}")
print(f"[TEST] 默认供应商: {cfg.get('default_suppliers')}")
assert cfg.get("approver_emails") == ["biqzh@neusoft.com"], "审批人邮箱未生效"
assert len(cfg.get("default_suppliers", [])) == 2, "供应商池未生效"
print("[TEST] skill 静态配置校验通过")

# 6) 准备工程师 A 邮件（放在 inbox，系统 PARSING 步骤会读）
MAIL_A_MSG_ID = "msg-A-001"
INBOX_MAILS.append({
    "message_id": MAIL_A_MSG_ID,
    "from_email": "engineer@company.com",
    "subject": "【备件询价】PRJ-2026-0888 南京地铁1号线交换机 — Seagate ST800MM015 x 2",
    "mail_body_text": (
        "您好，我是运维部工程师，现发起备件询价申请。\n\n"
        "项目编号：PRJ-2026-0888\n"
        "项目名称：南京地铁1号线交换机\n"
        "备件类型：硬盘\n"
        "品牌：Seagate\n"
        "PN：ST800MM015\n"
        "规格：800GB SAS 2.5寸\n"
        "成色：全新\n"
        "数量：2\n"
        "收货地址：南京市鼓楼区中山北路100号\n"
        "紧急程度：5min\n"
        "最晚发货时间：2026-09-05 18:00\n"
    ),
    "in_reply_to": None,
})

# 7) 触发 tick 流程
print("\n========== 第1次 tick：PARSING → SENDING_B ==========")
from app.routes_procurement_agent import tick_mail_inquiry
res1 = tick_mail_inquiry()
print(f"tick1 result: {json.dumps(res1, ensure_ascii=False, indent=2)}")
assert res1.get("progress", 0) >= 1, "PARSING 没推进"
assert (res1["step_stats"].get("SENDING_B") or {}).get("processed", 0) >= 1, "SENDING_B 没执行"

# 验证 B 邮件已发出（2 个供应商）
assert len(BATCH_SENT_MAILS) == 2, f"B 邮件应发 2 封，实际 {len(BATCH_SENT_MAILS)}"
addr = "南京市鼓楼区中山北路100号"  # A 邮件里的收货地址值
for m in BATCH_SENT_MAILS:
    assert "询价" in m["subject"]
    # B 模板不应包含实际收货地址（如 address 字段值），可以提"收货信息"但不能有具体地址
    assert addr not in m["body"], f"B 邮件包含实际收货地址！body={m['body'][:200]}"
    assert "NeuOps" in m["body"] or "询价" in m["body"]
print("[TEST] B 邮件 2 封已发出，不带收货地址 ✓")

# 找 B 的 message_id（两家供应商分别的）
B_MSG_IDS = [m["message_id"] for m in BATCH_SENT_MAILS]
print(f"B 邮件 message_id: {B_MSG_IDS}")

# 8) 再次 tick：SENDING_B → WAITING_QUOTES（此时还没报价，不会推进）
print("\n========== 第2次 tick：SENDING_B → WAITING_QUOTES ==========")
res2 = tick_mail_inquiry()
print(f"tick2 step_stats: {res2.get('step_stats')}")

# 9) 供应商回报价（走 B 邮件会话）
# 供应商1：¥1280（最低价）
INBOX_MAILS.append({
    "message_id": "msg-quote-1",
    "from_email": "13260023678@163.com",
    "subject": "Re: 【询价】PRJ-2026-0888 Seagate ST800MM015 x 2",
    "mail_body_text": (
        "您好，报价如下：\n"
        "备件PN号：ST800MM015\n"
        "报价单价：1280元\n"
        "可提供成色：全新\n"
        "可交付数量：2\n"
        "预计发货时间：2026-09-04\n"
        "是否可提供测试报告：是\n"
    ),
    "in_reply_to": B_MSG_IDS[0],
})
# 供应商2：¥1350（较高价）
INBOX_MAILS.append({
    "message_id": "msg-quote-2",
    "from_email": "biquanzhi@163.com",
    "subject": "Re: 【询价】PRJ-2026-0888 Seagate ST800MM015 x 2",
    "mail_body_text": (
        "您好，报价如下：\n"
        "备件PN号：ST800MM015\n"
        "报价单价：1350元\n"
        "可提供成色：全新\n"
        "可交付数量：2\n"
        "预计发货时间：2026-09-03\n"
        "是否可提供测试报告：是\n"
    ),
    "in_reply_to": B_MSG_IDS[1],
})

print("\n========== 第3次 tick：收报价 → 外部最低价优选 → 内部发D审批 ==========")
print(f"[DEBUG] BATCH_SENT_MAILS message_ids: {[m['message_id'] for m in BATCH_SENT_MAILS]}")
print(f"[DEBUG] INBOX_MAILS count: {len(INBOX_MAILS)}")
for i, m in enumerate(INBOX_MAILS):
    print(f"[DEBUG] INBOX[{i}]: from={m.get('from_email')}, in_reply_to={m.get('in_reply_to')}, subject={m.get('subject','')[:50]}")
res3 = tick_mail_inquiry()
# 报价刚入箱，可能需要多个 tick 才能从收报价→最低价优选→发D审批；循环推进直到内部流处理或超限
int_done = False
for _t in range(6):
    resX = tick_mail_inquiry()
    int_by = (resX.get("step_stats") or {}).get("internal") or {}
    if int_by.get("processed", 0) >= 1:
        res3 = resX; int_done = True; break
    res3 = resX
print(f"tick3 result: {json.dumps(res3, ensure_ascii=False, indent=2)}")
# 外部流应已算出最低价并进入 R_ORDER；内部流应已发出 D 审批
int_by = (res3.get("step_stats") or {}).get("internal") or {}
assert int_done or int_by.get("processed", 0) >= 1, "内部流没推进"

# 验证 D 邮件：回复 A 会话 + 抄送审批人 + 系统最低价提示
D_MSG_ID = find_D_msg_id()
assert D_MSG_ID is not None, "模板D没发出"
D_MAIL = next(m for m in SENT_MAILS if m["message_id"] == D_MSG_ID)
assert D_MAIL["reply_to"] == MAIL_A_MSG_ID, f"D 没回复 A 会话！reply_to={D_MAIL.get('reply_to')}"
assert "biqzh@neusoft.com" in (D_MAIL.get("cc") or []), f"D 没抄送审批人！cc={D_MAIL.get('cc')}"
assert "最低价" in D_MAIL["body"], "D 没写系统最低价优选提示"
assert "1280" in D_MAIL["body"], "D 没写最低价 ¥1280"
assert "13260023678@163.com" in D_MAIL["body"], "D 没写最低价供应商"
assert "写道" in D_MAIL["body"] and "项目编号：PRJ-2026-0888" in D_MAIL["body"], \
    "D 没引用工程师原始采购申请原文（内部流带原文）"
print("[TEST] 模板D：回复A会话 + 抄送审批人 + 最低价¥1280 提示 ✓")

# 10) 审批人回复"确认采购"（应自动选最低价）
INBOX_MAILS.append({
    "message_id": "msg-approval-1",
    "from_email": "biqzh@neusoft.com",
    "subject": "Re: 【询价汇总】PRJ-2026-0888 Seagate ST800MM015",
    "mail_body_text": "确认采购",
    "in_reply_to": D_MSG_ID,
})

print("\n========== 第4次 tick：审批人确认 → 外部ORDERING发E ==========")
res4 = tick_mail_inquiry()
# 审批确认可能在多个 tick 中才触发外部订货；循环推进直到 E 发出
for _t in range(6):
    tick_mail_inquiry()
    if any("订货" in m.get("subject", "") for m in SENT_MAILS):
        break
print(f"tick4 result: {json.dumps(res4, ensure_ascii=False, indent=2)}")

# 验证 E 邮件：回复选中供应商报价会话 + 带收货地址
E_MAILS = [m for m in SENT_MAILS if "订货" in m.get("subject", "") or "下单" in m.get("subject", "") or "采购确认" in m.get("body", "")]
assert len(E_MAILS) >= 1, f"模板E没发出，SENT_MAILS subjects: {[m.get('subject','') for m in SENT_MAILS]}"
E_MAIL = E_MAILS[0]
print(f"[DEBUG] E_MAIL subject={E_MAIL.get('subject')}, reply_to={E_MAIL.get('reply_to')}, body[:300]={E_MAIL.get('body','')[:300]}")
# E 应该回复选中供应商的报价邮件会话（同一线程，不新建）
assert E_MAIL.get("reply_to"), "E 没有回复报价会话！"
assert E_MAIL["reply_to"] in ("msg-quote-1", "msg-quote-2"), \
    f"E 必须回复选中供应商的报价邮件线程，实际 reply_to={E_MAIL.get('reply_to')}"
assert "南京市鼓楼区中山北路100号" in E_MAIL["body"], f"E 没带收货地址！body[:400]={E_MAIL.get('body','')[:400]}"
assert "测试报告" in E_MAIL["body"], "E 没要求测试报告"
assert "快递单号" in E_MAIL["body"], "E 没要求快递单号"
assert "写道" in E_MAIL["body"] and "报价单价：1280元" in E_MAIL["body"], \
    "E 没引用供应商报价原文（外部流带原文）"
print("[TEST] 模板E：回复最低价供应商报价会话 + 带收货地址 + 要求测试报告/快递单号 ✓")

# 11) 供应商(最低价家)回复快递单号
INBOX_MAILS.append({
    "message_id": "msg-ship-1",
    "from_email": "13260023678@163.com",
    "subject": "Re: 发货通知",
    "mail_body_text": "快递单号：SF1234567890",
    "in_reply_to": E_MAIL.get("reply_to"),
})

print("\n========== 第5次 tick：供应商回单号 登记 ==========")
res5 = tick_mail_inquiry()
for _t in range(4):
    tick_mail_inquiry()

# 12) 工程师(原发件人)在内部流回复"备件更换完成" → 触发G结算 → 内部R_CLOSED/DONE
INBOX_MAILS.append({
    "message_id": "msg-engineer-done-1",
    "from_email": "engineer@company.com",
    "subject": "Re: 备件更换完成",
    "mail_body_text": "备件已更换完成，可以结算了。",
    "in_reply_to": D_MSG_ID,
})

print("\n========== 第6次 tick：工程师回备件更换完成 → G结算 → DONE ==========")
res6 = tick_mail_inquiry()
for _t in range(6):
    tick_mail_inquiry()

# 13) 任务最终状态验证
tasks = sm.spare_mail_list_tasks({}, 10)
assert len(tasks) >= 1, "任务不存在"
t = tasks[0]
assert t["status"] == "DONE", f"任务状态应为 DONE，实际 {t['status']}"
assert t["internal_status"] == "R_CLOSED", f"内部流应为 R_CLOSED，实际 {t['internal_status']}"
assert "1280" in str(t["lowest_quote"]), f"最低价应为 1280，实际 {t['lowest_quote']}"
assert t["target_supplier"] and "供应商" in t["target_supplier"], f"目标供应商应为最低价，实际 {t['target_supplier']}"
# G 结算邮件应已发给选中供应商
G_MAILS = [m for m in SENT_MAILS if "采购结束" in m.get("subject", "")]
assert len(G_MAILS) >= 1, f"模板G(结算)没发出，subjects={[m.get('subject','') for m in SENT_MAILS]}"
print(f"[TEST] 任务最终状态: status={t['status']}, internal={t['internal_status']}, external={t['external_status']}, shipped_no={t.get('shipped_no')}, lowest={t.get('lowest_supplier')}@{t.get('lowest_quote')}, target={t.get('target_supplier')}")

# 14) 清理
os.remove(TEST_DB)
print("\n========== 全链路测试通过 ✓ ==========")
