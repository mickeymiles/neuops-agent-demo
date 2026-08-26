# ────────────────────────────────────────────
# Agent 对话链路：Mock Agent 执行 / DeepSeek 调用 / /api/chat SSE
# ────────────────────────────────────────────

import asyncio
import datetime
import json
import os
import time
import uuid

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .config import AGENT_ENGINE, BIZ_9006_BASE, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .dsh_engine import dsh_agent_run
from .db import (
    _COST_INPUT_PER_M,
    _COST_OUTPUT_PER_M,
    _db_lock,
    _get_conn,
    _load_chat_history,
    db_get_employee,
    db_get_employee_kb_ids,
    db_get_mcp_server,
    db_get_mcp_tool,
    db_list_employees,
    db_list_skills,
    ensure_conversation,
    save_agent_message,
    save_user_message,
)
from .devtools import DEV_TOOLS, _tool_result_summary, execute_dev_tool
from .knowledge import search_knowledge
from .mcp_tools import (
    ChatRequest,
)

router = APIRouter()


async def mock_agent_run(query: str, mode: str, selected_skill: str, approved_action: str = None, history: list = None, conversation_id: str = None):
    """模拟 Agent 执行过程，产生 SSE 事件流"""
    
    # 审批确认后的执行：AI 只研判不擅自变更，写/高危操作一律转人工执行
    if approved_action:
        yield sse_event("agent_thought", f"已收到对操作「{approved_action}」的人工确认意愿。按权限规范，AI 不具备自动执行权限，该变更已登记为待办，请运维人员手动执行。")
        yield sse_event("agent_message", {
            "content": f"""## ⚠️ 变更待人工执行

| 项目 | 详情 |
|------|------|
| 变更操作 | {approved_action} |
| 执行方式 | **人工执行**（AI 无自动执行权限） |
| 状态 | 已登记待办，待运维确认 |

**说明**：按权限安全规范，AI 数字员工不自动执行任何写操作/高危变更。请运维人员登录对应系统（9006/9007）手动执行该操作，完成后可在对话中继续跟进。""",
            "actions": [
                {"id": "open_ops", "label": "🔗 打开运维平台人工执行", "type": "link", "url": "http://127.0.0.1:9007/ops"}
            ]
        })
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ──── 定向技能模式 ────
    # skill-3（运维脚本与日志排障）等技能均已改为自由路由/通用循环（build_employee_tools + execute_configured_tool 真实执行 9007/9006）

    # ──── 采购清单比对 Skill（真实调用9006合同比对系统）────
    if mode == "skill" and selected_skill == "skill-10":
        BASE = "http://127.0.0.1:9006"
        
        yield sse_event("agent_thought", """任务分析：
1. 用户请求执行采购清单比对，已选择「采购清单比对Skill」
2. 需要从9006合同比对系统获取真实数据
3. 解析用户意图 → 查询合同列表 → 获取比对结果 → 生成报告
4. 执行模式：定向技能模式""")
        await asyncio.sleep(0.6)

        async with httpx.AsyncClient(timeout=30) as client:
            # ── 步骤1：获取真实合同列表 ──
            yield sse_event("agent_thought", "步骤1/3：正在连接9006合同比对系统，获取合同列表...")
            await asyncio.sleep(0.3)
            
            try:
                contracts_resp = await client.get(f"{BASE}/api/contracts")
                contracts_data = contracts_resp.json()
                all_contracts = contracts_data.get("contracts", [])
            except Exception as e:
                yield sse_event("agent_thought", f"⚠️ 无法连接9006系统：{e}")
                yield sse_event("agent_message", {
                    "content": f"## ⚠️ 合同比对系统连接失败\n\n无法访问 9006 端口服务，请确认服务是否正常运行。\n\n> 错误：{e}",
                    "actions": [{"id": "open_9006", "label": "🔗 打开9006系统", "type": "link", "url": f"{BASE}"}]
                })
                yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
                return

            yield sse_event("tool_call", {
                "tool": "query_contracts",
                "source": "9006合同比对系统",
                "total_contracts": len(all_contracts),
                "contracts": [{"name": c["contract_name"], "status": c["status"], "progress": c["progress"]} for c in all_contracts[:5]]
            })

            # ── 步骤2：匹配用户提到的合同 ──
            # 尝试从用户query中提取合同名关键词
            contract_keywords = ["雷神", "药监", "国药", "亿道", "测试"]
            matched_contract = None
            for c in all_contracts:
                name = c.get("contract_name", "")
                # 精确匹配或关键词匹配
                for kw in contract_keywords:
                    if kw in query or kw in name:
                        if (kw in query and kw in name) or query in name:
                            matched_contract = c
                            break
                if matched_contract:
                    break
            
            # 如果没匹配到，取最近有比对结果的那个
            if not matched_contract:
                for c in all_contracts:
                    if c.get("progress", 0) > 0:
                        matched_contract = c
                        break
                if not matched_contract and all_contracts:
                    matched_contract = all_contracts[0]

            cid = matched_contract["id"]
            cname = matched_contract["contract_name"]
            cstatus = matched_contract["status"]
            supplier_name = matched_contract.get("latest_supplier", "未上传")

            yield sse_event("agent_thought", f"""步骤2/3：已定位目标合同
- 合同名称：{cname}
- 合同编号：{matched_contract.get('contract_no', 'N/A')}
- 当前状态：{cstatus}
- 供应商：{supplier_name}
- 比对进度：{matched_contract.get('progress', 0)}%

正在拉取详细比对结果...""")
            await asyncio.sleep(0.6)

            # ── 步骤3：获取真实比对结果 ──
            try:
                stats_resp = await client.get(f"{BASE}/api/contract/{cid}/stats")
                stats = stats_resp.json().get("stats", {})
                
                results_resp = await client.get(f"{BASE}/api/contract/{cid}/compare/results")
                results_data = results_resp.json()
                results = results_data.get("results", [])
                total = results_data.get("total", 0)
            except Exception as e:
                yield sse_event("agent_thought", f"⚠️ 获取比对结果失败：{e}")
                yield sse_event("agent_message", {
                    "content": f"## ⚠️ 比对结果获取异常\n\n合同「{cname}」已定位，但获取比对详情时出错。\n\n> 请直接访问9006系统查看：{BASE}",
                    "actions": [{"id": "open_9006", "label": "🔗 打开9006系统", "type": "link", "url": f"{BASE}"}]
                })
                yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
                return

            yield sse_event("tool_call", {
                "tool": "get_comparison_results",
                "contract": cname,
                "total_items": total,
                "matched": stats.get("matched_count", 0),
                "anomaly": stats.get("anomaly_count", 0),
                "pending": stats.get("pending_count", 0),
                "extra": stats.get("extra_count", 0),
                "progress": stats.get("progress", 0),
                "source": "9006真实比对引擎"
            })

            # ── 步骤4：汇总报告 ──
            yield sse_event("agent_thought", "步骤3/3：正在基于真实比对数据生成分析报告...")
            await asyncio.sleep(0.8)

            # 分类统计
            matched_count = stats.get("matched_count", 0)
            anomaly_count = stats.get("anomaly_count", 0)
            pending_count = stats.get("pending_count", 0)
            extra_count = stats.get("extra_count", 0)
            progress = stats.get("progress", 0)
            contract_total = stats.get("contract_total", total)
            
            match_rate = round(matched_count / max(contract_total, 1) * 100, 1)

            # 提取差异明细（实时数据）
            anomaly_items = [r for r in results if r.get("match_status") != "匹配成功"]
            # 按类别分组
            from collections import Counter
            status_counter = Counter(r.get("match_status", "未知") for r in results)
            
            # 构建报告
            report_lines = [
                "## 📊 采购清单比对报告",
                "",
                f"**合同名称**：{cname}  ",
                f"**合同编号**：{matched_contract.get('contract_no', 'N/A')}  ",
                f"**供应商**：{supplier_name}  ",
                f"**状态**：{cstatus}  ",
                f"**比对项数**：{contract_total} 项  ",
                f"**匹配率**：{match_rate}%（{matched_count}/{contract_total}）",
                "",
                "---",
                "",
                "### 一、比对结果总览",
                "",
                "| 状态 | 数量 | 占比 |",
                "|------|------|------|",
            ]
            
            status_labels = {
                "匹配成功": f"✅ 完全匹配 | {status_counter.get('匹配成功', 0)} | {round(status_counter.get('匹配成功',0)/max(total,1)*100,1)}%",
                "匹配异常": f"⚠️ 匹配异常 | {anomaly_count} | {round(anomaly_count/max(contract_total,1)*100,1)}%",
                "待采购": f"❌ 供应商未报价 | {pending_count} | {round(pending_count/max(contract_total,1)*100,1)}%",
                "供应商增项": f"📌 供应商增项 | {extra_count} | {round(extra_count/max(contract_total,1)*100,1)}%",
            }
            for status_key in ["匹配成功", "匹配异常", "待采购", "供应商增项"]:
                if status_counter.get(status_key, 0) > 0:
                    report_lines.append(f"| {status_labels[status_key]} |")

            report_lines.extend([
                "",
                "### 二、差异明细（真实数据来源：9006比对引擎）",
                "",
            ])

            if anomaly_items:
                # 合并同类差异显示
                anomaly_by_type = {}
                for item in anomaly_items:
                    status = item.get("match_status", "未知")
                    name = item.get("ct_name") or item.get("sp_name", "未知")
                    detail = item.get("anomaly_detail", "")
                    key = f"{status}|{name}"
                    if key not in anomaly_by_type:
                        anomaly_by_type[key] = {"count": 0, "detail": detail, "status": status, "name": name}
                    anomaly_by_type[key]["count"] += 1
                
                report_lines.append("| 设备名称 | 差异类型 | 数量 | 说明 |")
                report_lines.append("|----------|---------|------|------|")
                status_emoji = {"待采购": "❌", "匹配异常": "⚠️", "供应商增项": "📌"}
                for key, item in sorted(anomaly_by_type.items()):
                    emoji = status_emoji.get(item["status"], "•")
                    detail_short = item["detail"][:60] + ("..." if len(item.get("detail","")) > 60 else "")
                    report_lines.append(f"| {item['name']} | {emoji} {item['status']} | {item['count']} | {detail_short} |")
                
                if len(anomaly_by_type) > 20:
                    report_lines.append(f"| ... | 还有 {len(anomaly_by_type)-20} 类差异 | ... | 请在9006系统查看完整明细 |")
            else:
                report_lines.append("> ✅ 所有合同项与供应商报价完全匹配，无差异项。")

            report_lines.extend([
                "",
                "### 三、评审建议",
                "",
            ])
            
            if pending_count > 0:
                report_lines.append(f"1. **供应商未报价 {pending_count} 项**：占合同总量 {round(pending_count/max(contract_total,1)*100,1)}%，需联系供应商补充报价。")
                # 列出主要未报价类别（取前5）
                pending_items = [r for r in results if r.get("match_status") == "待采购"]
                pending_names = list(set(r.get("ct_name", "未知") for r in pending_items))[:5]
                report_lines.append(f"   主要缺失项：{'、'.join(pending_names)}")
            
            if anomaly_count > 0:
                report_lines.append(f"2. **匹配异常 {anomaly_count} 项**：需逐项人工确认，可在9006系统中标记「已确认」。")
            
            if progress >= 100:
                report_lines.append("3. 该合同已全部比对完毕，可直接导出Excel报告。")
            else:
                report_lines.append(f"3. 当前比对进度 {progress}%，尚有 {contract_total - matched_count - anomaly_count - pending_count - extra_count} 项待处理。")

            report_lines.extend([
                "",
                "---",
                "",
                "> 💡 **数据来源**：以上所有数据均来自9006合同比对系统真实API",
                f"> 📋 [查看9006系统完整明细]({BASE}) | 📊 [导出Excel报告]({BASE}/api/contract/{cid}/export/report?version_id={stats.get('version_id', '')})",
            ])

            report = "\n".join(report_lines)
            
            yield sse_event("agent_message", {
                "content": report,
                "actions": [
                    {"id": "view_9006", "label": "🔗 查看9006系统完整明细", "type": "link", "url": f"{BASE}"},
                    {"id": "export_report", "label": "📊 导出Excel报告", "type": "link", "url": f"{BASE}/api/contract/{cid}/export/report?version_id={stats.get('version_id', '')}"},
                ]
            })
        
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ──── 经营指标分析 Skill（调9006指标数据集MCP）────
    if mode == "skill" and selected_skill == "skill-11":
        BASE = "http://127.0.0.1:9006"
        yield sse_event("agent_thought", """任务分析：
1. 用户选择「经营指标分析Skill」，查询经营指标
2. 通过9006指标数据集MCP读取定时ETL预计算的指标宽表
3. 目标指标：签单毛利率（按年份维度）
4. 指标口径以9006定时任务计算为准，本Skill只做解读不做原始聚合""")
        await asyncio.sleep(0.6)
        yield sse_event("agent_thought", "步骤：调用指标数据集MCP → GET /api/etl/metrics（签单毛利率，按年份）...")
        await asyncio.sleep(0.4)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{BASE}/api/etl/metrics", params={"job_key": "gross-margin", "dim_type": "year"})
                data = r.json()
            metrics = data.get('metrics', [])
        except Exception:
            metrics = []
        if not metrics:
            yield sse_event("agent_message", {
                "content": f"## ⚠️ 指标数据获取失败\n\n无法连接9006指标数据集MCP，或指标宽表尚未计算。\n\n> 请先在9006执行定时任务「签单毛利指标计算」，或打开 {BASE} 查看。",
                "actions": [{"id": "open_9006", "label": "🔗 打开9006系统", "type": "link", "url": BASE}]
            })
            yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
            return
        yield sse_event("tool_call", {"tool": "get_etl_metrics", "source": "9006指标数据集MCP", "job_key": "gross-margin", "dim_type": "year", "rows": len(metrics)})
        await asyncio.sleep(0.6)
        by_year = {m['year']: m for m in metrics}
        years = sorted([y for y in by_year.keys() if y.isdigit()])
        recent = years[-3:] if len(years) >= 3 else years
        lines = ["## 📈 签单毛利经营分析报告", "", "**数据来源**：9006 指标数据集MCP（定时ETL预计算宽表）", "", "| 年份 | 合同额(万) | 签单毛利(万) | 签单毛利率 |", "|------|-----------:|-------------:|-----------:|"]
        for y in recent:
            m = by_year[y]
            lines.append(f"| {y} | {m['contract_amt']/10000:.0f} | {m['gross_profit']/10000:.0f} | {m['gross_rate']*100:.2f}% |")
        if len(recent) >= 2:
            cur = by_year[recent[-1]]; prev = by_year[recent[-2]]
            diff = (cur['gross_rate'] - prev['gross_rate']) * 100
            lines.append("")
            lines.append(f"**同比解读**：{recent[-1]} 年签单毛利率 {cur['gross_rate']*100:.2f}%，较 {recent[-2]} 年 {prev['gross_rate']*100:.2f}% {'上升' if diff >= 0 else '下降'} {abs(diff):.2f} 个百分点。")
        lines.append("")
        lines.append("> 💡 指标口径以9006定时任务计算为准，本报告仅做解读，不自行重算。")
        yield sse_event("agent_message", {
            "content": "\n".join(lines),
            "actions": [{"id": "view_9006", "label": "🔗 查看9006完整指标", "type": "link", "url": BASE}]
        })
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ──── 合同明细探查 Skill（调9006原子本体MCP）────
    if mode == "skill" and selected_skill == "skill-12":
        import re as _re
        BASE = "http://127.0.0.1:9006"
        kw = ""
        m = _re.search(r'[A-Za-z]{2,}[0-9A-Za-z]{4,}', query)
        if m:
            kw = m.group(0)
        yield sse_event("agent_thought", f"""任务分析：
1. 用户选择「合同明细探查Skill」，探查原始合同明细
2. 通过9006原子本体MCP查询原始明细表（只读）
3. 提取查询关键词：{kw or '（未识别，将查询全部）'}
4. 目标表：总合同表（付款/收款明细表可通过数据源管理上传）""")
        await asyncio.sleep(0.6)
        yield sse_event("agent_thought", f"步骤：调用原子本体MCP → GET /api/mcp/ontology/query（总合同表，关键词={kw or '全部'}）...")
        await asyncio.sleep(0.4)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{BASE}/api/mcp/ontology/query", params={"table_name": "总合同表", "keyword": kw, "limit": 20})
                data = r.json()
            rows = data.get('rows', []); headers = data.get('headers', [])
        except Exception:
            rows, headers = [], []
        if not rows:
            yield sse_event("agent_message", {
                "content": f"## ⚠️ 明细探查无结果\n\n未查询到与「{kw}」匹配的合同明细。\n\n> 请确认关键词，或打开 {BASE} 数据源管理查看。",
                "actions": [{"id": "open_9006", "label": "🔗 打开9006系统", "type": "link", "url": BASE}]
            })
            yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
            return
        yield sse_event("tool_call", {"tool": "query_ontology", "source": "9006原子本体MCP", "table_name": "总合同表", "keyword": kw, "rows": len(rows)})
        await asyncio.sleep(0.6)

        def _cidx(name):
            for i, h in enumerate(headers):
                if name in h: return i
            return None
        i_no = _cidx('合同编号'); i_amt = _cidx('合同总金额'); i_gross = _cidx('签单毛利'); i_date = _cidx('统计日期')
        lines = ["## 📋 合同明细探查结果", "", f"**查询关键词**：{kw or '全部'}　**命中**：{len(rows)} 条", "", "| 合同编号 | 合同总金额 | 签单毛利 | 统计日期 |", "|---------|-----------:|---------:|---------|"]
        for r in rows[:10]:
            no = r[i_no] if i_no is not None and i_no < len(r) else '-'
            amt = r[i_amt] if i_amt is not None and i_amt < len(r) else ''
            gross = r[i_gross] if i_gross is not None and i_gross < len(r) else ''
            dt = r[i_date] if i_date is not None and i_date < len(r) else ''
            lines.append(f"| {no} | {amt} | {gross} | {dt} |")
        lines.append("")
        lines.append(f"> 💡 明细数据来自9006原子本体MCP（只读原始表），共 {data.get('count', len(rows))} 条。")
        yield sse_event("agent_message", {
            "content": "\n".join(lines),
            "actions": [{"id": "view_9006", "label": "🔗 打开9006数据源管理", "type": "link", "url": BASE}]
        })
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ──── 自由 Agent 模式（真实 DeepSeek：意图识别 + 数字员工路由 + tool calling）────
    yield sse_event("agent_thought", "🧠 主智能体正在识别任务意图，进行数字员工路由...")

    route_system = build_route_system_prompt()
    # 主路由带最近 2 轮历史，帮助理解追问/指代（如"那错误率呢"）
    route_history = (history or [])[-4:]
    route_resp = await deepseek_chat(
        [{"role": "system", "content": route_system}] + route_history + [{"role": "user", "content": query}],
        tools=build_route_tools(), temperature=0, max_tokens=800,
        trace_ctx={"conversation_id": conversation_id, "stage": "intent_route",
                   "employee_id": "", "employee_name": "意图路由"})
    employee = "emp-001"
    route_reason = ""
    if "error" in route_resp:
        yield sse_event("agent_thought", "⚠️ 意图识别调用失败：" + str(route_resp["error"]))
    else:
        rmsg = route_resp["choices"][0]["message"]
        rtc = rmsg.get("tool_calls")
        if rtc:
            try:
                rargs = json.loads(rtc[0]["function"]["arguments"])
                employee = rargs.get("employee", "emp-001")
                route_reason = rargs.get("reason", "")
            except Exception:
                pass
        if rmsg.get("reasoning_content"):
            yield sse_event("agent_thought", "💭 主智能体思考：" + rmsg["reasoning_content"])

    if employee == "emp-004":
        yield sse_event("route", {"employee": "emp-004", "name": "经营业务分析专家", "reason": route_reason or "经营业务类任务"})
        yield sse_event("agent_thought", f"""✅ 意图识别完成：路由到【经营业务分析专家 emp-004】
理由：{route_reason or '经营业务类任务'}""")

        emp_system = build_employee_prompt("emp-004") + build_rag_context(query, "emp-004", conversation_id=conversation_id, employee_name="经营业务分析专家")
        messages = [{"role": "system", "content": emp_system}] + (history or []) + [{"role": "user", "content": query}]
        emp_tools = build_employee_tools("emp-004")
        exec_ctx = {"conversation_id": conversation_id, "stage": "agent_exec",
                    "employee_id": "emp-004", "employee_name": "经营业务分析专家"}

        for _round in range(15):
            resp = await deepseek_chat(messages, tools=emp_tools, temperature=0.2, max_tokens=8000, model="deepseek-chat",
                                       trace_ctx=exec_ctx, round_no=_round)
            if "error" in resp:
                yield sse_event("agent_thought", "⚠️ emp-004 调用失败：" + str(resp["error"]))
                break
            msg = resp["choices"][0]["message"]
            reasoning = msg.get("reasoning_content", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            if reasoning:
                yield sse_event("agent_thought", "💭 emp-004 思考：" + reasoning)
            elif content and tool_calls:
                yield sse_event("agent_thought", "💭 emp-004 计划：" + content)
            if tool_calls:
                messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc["function"]["name"]
                    try:
                        fargs = json.loads(tc["function"]["arguments"])
                    except Exception:
                        fargs = {}
                    yield sse_event("tool_call", {"tool": fn, **fargs})
                    _t0 = time.time()
                    try:
                        result = await execute_configured_tool(fn, fargs)
                        _record_tool_call(exec_ctx, _round, fn, fargs, result=result,
                                          latency_ms=(time.time() - _t0) * 1000)
                    except Exception as _e:
                        _record_tool_call(exec_ctx, _round, fn, fargs, success=False, error=str(_e),
                                          latency_ms=(time.time() - _t0) * 1000)
                        result = {"error": str(_e)}
                    yield sse_event("tool_result", _tool_result_summary(fn, result))
                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": json.dumps(result, ensure_ascii=False)})
            else:
                if content:
                    yield sse_event("agent_message", {"content": content, "actions": [
                        {"id": "open_9006", "label": "🔗 打开9006经营分析系统", "type": "link", "url": "http://127.0.0.1:9006"}
                    ]})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 未生成有效结论

模型未返回最终答案，请重试。"""})
                break
        else:
            # 达到轮次上限但未收敛：追加一次"总结调用"，基于已收集的工具结果输出兜底结论
            yield sse_event("agent_thought", "⚠️ 已进行多轮工具查询，现根据已收集的结果生成最终结论...")
            messages.append({"role": "user", "content": "你已通过多轮工具调用收集了大量数据，但尚未输出最终结论。"
                                                        "现在请不要再调用任何工具，直接基于以上所有工具返回的真实结果，"
                                                        "用 Markdown 中文输出最终分析结论（包含必要的数据表格、分组对比与简短结论）。"})
            try:
                resp = await deepseek_chat(messages, tools=None, temperature=0.2, max_tokens=4000,
                                           model="deepseek-chat",
                                           trace_ctx={"conversation_id": conversation_id, "stage": "agent_exec_fallback",
                                                      "employee_id": "emp-004", "employee_name": "经营业务分析专家"},
                                           round_no=_round + 1)
                if "error" not in resp:
                    fallback_content = resp["choices"][0]["message"].get("content", "")
                    if fallback_content:
                        yield sse_event("agent_message", {"content": fallback_content, "actions": [
                            {"id": "open_9006", "label": "🔗 打开9006经营分析系统", "type": "link", "url": "http://127.0.0.1:9006"}
                        ]})
                    else:
                        yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已收集多轮工具查询结果，但模型未能整理出最终结论。可查看上方工具调用记录，或简化需求后重试。"""})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具查询但未收敛，请简化需求重试。"""})
            except Exception as _e:
                yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具查询但未收敛，请简化需求重试。"""})

        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ── 路由到业务平台编辑辅助专家 emp-005（必选：合同比对 + 9006 有限规则配置修改方案，人工确认后生效）──
    if employee == "emp-005":
        yield sse_event("route", {"employee": "emp-005", "name": "业务平台编辑辅助专家", "reason": route_reason or "平台编辑/研发类任务"})
        yield sse_event("agent_thought", f"""✅ 意图识别完成：路由到【业务平台编辑辅助专家 emp-005】
理由：{route_reason or '平台编辑/研发类任务'}""")

        emp_system = ("你是「业务平台编辑辅助专家 emp-005」数字员工（必选），负责辅助9006经营业务分析系统的文件解析比对与有限规则配置修改。"
                      "你有两类真实能力：\n"
                      "【A. 合同比对（9006 真实数据，只读）】query_contracts 查合同列表；get_comparison_results 查比对结果（match_type/是否异常/是否缺项）；"
                      "get_contract_stats 查比对统计；export_report 导出比对报告。用户询问合同比对结果/差异分析时使用。\n"
                      "【B. 9006 规则配置辅助（只读 + 生成变更方案）】list_project_files/search_code/read_code_file 三个工具只读查看 9006 项目"
                      "（/home/ubuntu/contract-compare）中计算规则、排除规则、比对开关、过滤条件等规则配置的现状，"
                      "理解业务口径后，生成规则配置变更方案（如：新增某类数据排除规则、关闭价格比对规则、调整参数匹配/过滤逻辑等），"
                      "并输出变更前后配置对比与业务影响评估，供人工审核确认。\n"
                      "工作方式：先判断用户需求属于合同比对还是规则配置辅助；比对类直接查9006真实结果做差异分析；"
                      "规则配置类先 list_project_files 了解结构 → search_code 定位规则逻辑所在文件 → read_code_file 读取相关规则现状 → 说明当前口径 → 生成规则配置变更方案（含变更前后对比与业务影响）→ 提示需人工确认审批。\n"
                      "红线（必须遵守）：① 严禁修改合同、付款等原始业务数据表；② 严禁直接修改9006代码——AI只产出规则配置变更方案；"
                      "③ 所有规则配置变更必须人工确认审批后才可调用MCP写入规则配置生效；④ 不编造「已生效」——人工确认后配置才算真正变更。") \
                      + build_rag_context(query, "emp-005", conversation_id=conversation_id, employee_name="业务平台编辑辅助专家")
        messages = [{"role": "system", "content": emp_system}] + (history or []) + [{"role": "user", "content": query}]
        exec_ctx = {"conversation_id": conversation_id, "stage": "agent_exec",
                    "employee_id": "emp-005", "employee_name": "业务平台编辑辅助专家"}
        _BIZ_TOOLS_005 = ["query_contracts", "get_comparison_results", "get_contract_stats", "export_report"]
        _READONLY_DEV_TOOLS_005 = [t for t in DEV_TOOLS if t["function"]["name"] in ("list_project_files", "search_code", "read_code_file")]
        _EMP005_TOOLS = _READONLY_DEV_TOOLS_005 + [
            {"type": "function", "function": {"name": "query_contracts",
                                              "description": "查询9006合同比对系统的合同列表（真实数据）",
                                              "parameters": {"type": "object", "properties": {"keyword": {"type": "string", "description": "合同关键字"}}, "required": []}}},
            {"type": "function", "function": {"name": "get_comparison_results",
                                              "description": "查询指定合同的比对结果明细（match_type/异常/缺项）",
                                              "parameters": {"type": "object", "properties": {"contract_id": {"type": "string", "description": "合同ID"}, "page": {"type": "integer", "description": "页码"}}, "required": ["contract_id"]}}},
            {"type": "function", "function": {"name": "get_contract_stats",
                                              "description": "查询指定合同的比对统计（完全匹配/异常/待采购/供应商增项）",
                                              "parameters": {"type": "object", "properties": {"contract_id": {"type": "string", "description": "合同ID"}}, "required": ["contract_id"]}}},
            {"type": "function", "function": {"name": "export_report",
                                              "description": "导出指定合同的比对报告",
                                              "parameters": {"type": "object", "properties": {"contract_id": {"type": "string", "description": "合同ID"}}, "required": ["contract_id"]}}},
        ]

        for _round in range(20):
            resp = await deepseek_chat(messages, tools=_EMP005_TOOLS, temperature=0.2, max_tokens=8000, model="deepseek-chat",
                                       trace_ctx=exec_ctx, round_no=_round)
            if "error" in resp:
                yield sse_event("agent_thought", "⚠️ emp-005 调用失败：" + str(resp["error"]))
                break
            msg = resp["choices"][0]["message"]
            reasoning = msg.get("reasoning_content", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            if reasoning:
                yield sse_event("agent_thought", "💭 emp-005 思考：" + reasoning)
            elif content and tool_calls:
                yield sse_event("agent_thought", "💭 emp-005 计划：" + content)
            if tool_calls:
                messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc["function"]["name"]
                    try:
                        fargs = json.loads(tc["function"]["arguments"])
                    except Exception:
                        fargs = {}
                    yield sse_event("tool_call", {"tool": fn, **fargs})
                    _t0 = time.time()
                    try:
                        if fn in _BIZ_TOOLS_005:
                            result = await execute_configured_tool(fn, fargs)
                        else:
                            result = await execute_dev_tool(fn, fargs)
                        _record_tool_call(exec_ctx, _round, fn, fargs, result=result,
                                          latency_ms=(time.time() - _t0) * 1000)
                    except Exception as _e:
                        _record_tool_call(exec_ctx, _round, fn, fargs, success=False, error=str(_e),
                                          latency_ms=(time.time() - _t0) * 1000)
                        result = {"error": str(_e)}
                    yield sse_event("tool_result", _tool_result_summary(fn, result))
                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": json.dumps(result, ensure_ascii=False)})
            else:
                if content:
                    yield sse_event("agent_message", {"content": content, "actions": [
                        {"id": "open_9006", "label": "🔗 打开9006系统查看规则配置", "type": "link", "url": "http://127.0.0.1:9006"}
                    ]})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 未生成有效结论

模型未返回最终答案，请重试。"""})
                break
        else:
            # 达到轮次上限但未收敛：追加一次"总结调用"，基于已收集的工具结果输出兜底结论
            yield sse_event("agent_thought", "⚠️ 已进行多轮工具调用，现根据已收集的结果生成最终结论...")
            messages.append({"role": "user", "content": "你已通过多轮工具调用完成了9006规则配置现状梳理与变更方案分析，但尚未输出最终结论。"
                                                        "现在请不要再调用任何工具，直接基于以上所有工具返回的真实结果，"
                                                        "用 Markdown 中文输出最终交付说明：当前9006规则配置现状、建议的规则配置变更方案（含变更前后对比与业务影响评估）、必须人工确认审批后才可生效的提醒。"})
            try:
                resp = await deepseek_chat(messages, tools=None, temperature=0.2, max_tokens=4000,
                                           model="deepseek-chat",
                                           trace_ctx={"conversation_id": conversation_id, "stage": "agent_exec_fallback",
                                                      "employee_id": "emp-005", "employee_name": "业务平台编辑辅助专家"},
                                           round_no=_round + 1)
                if "error" not in resp:
                    fallback_content = resp["choices"][0]["message"].get("content", "")
                    if fallback_content:
                        yield sse_event("agent_message", {"content": fallback_content, "actions": [
                            {"id": "open_9006", "label": "🔗 打开9006系统查看规则配置", "type": "link", "url": "http://127.0.0.1:9006"}
                        ]})
                    else:
                        yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已收集多轮工具调用结果，但模型未能整理出最终结论。可查看上方工具调用记录，或简化需求后重试。"""})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具调用但未收敛，请简化需求重试。"""})
            except Exception as _e:
                yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具调用但未收敛，请简化需求重试。"""})

        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ── 路由到运维/开发类数字员工（emp-001 运维巡检 / emp-002 告警根因 / emp-003 运维开发助手）──
    #    全部走通用真实循环：build_employee_prompt + build_employee_tools + execute_configured_tool
    #    数据源：9007 一体化监控平台（实体/指标/日志/告警/事件/AI自监控），全部只读研判
    _emp_meta = {
        "emp-001": ("运维巡检专家", "http://127.0.0.1:9007/ops"),
        "emp-002": ("告警根因分析专家", "http://127.0.0.1:9007/ops"),
        "emp-003": ("运维开发助手", "http://127.0.0.1:9007/ops"),
        "emp-006": ("项目管理成本利润治理专家", "http://127.0.0.1:9007/ops"),
        "emp-007": ("售前投标方案智能组装专家", "http://127.0.0.1:9007/bidding"),
    }
    emp_name, emp_url = _emp_meta.get(employee, (employee, "http://127.0.0.1:9007"))
    async for ev in _run_employee_general_loop(employee, emp_name, query, history, conversation_id,
                                               route_reason, open_url=emp_url):
        yield ev
    return


def sse_event(event: str, data):
    """构造 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════
# DeepSeek 真实 LLM 调用层（真实 AgenticOps）
# ═══════════════════════════════════════════

_DEEPSEEK_KEY = ""


def _load_deepseek_key():
    """从环境变量或 .env 文件读取 DeepSeek API Key"""
    global _DEEPSEEK_KEY
    if _DEEPSEEK_KEY:
        return _DEEPSEEK_KEY
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        for p in (os.path.expanduser("~/.hermes/.env"),
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        line = line[7:] if line.startswith("export ") else line
                        if line.startswith("DEEPSEEK_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass
            if key:
                break
    _DEEPSEEK_KEY = key
    return key


def _record_llm_call(trace_ctx, model, payload, resp, latency_s, error="", round_no=0):
    """将一次 LLM 调用的 token/耗时/内容摘要/成本/温度/工具写入 llm_calls 观测表。
    成功调用必须有 usage；失败调用（error 非空）也入库，供告警/错误率统计。"""
    try:
        if not trace_ctx:
            return
        prompt_tk = completion_tk = total_tk = 0
        output = ""
        if isinstance(resp, dict):
            usage = resp.get("usage") or {}
            prompt_tk = int(usage.get("prompt_tokens") or 0)
            completion_tk = int(usage.get("completion_tokens") or 0)
            total_tk = int(usage.get("total_tokens") or 0)
            try:
                _msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
                output = (_msg.get("content") or "")[:1000]
            except Exception:
                pass
        if not error and total_tk <= 0:
            return
        # 输入摘要：system 前缀 + 各条 user 消息，截 2000 字符
        _input = ""
        try:
            _parts = []
            for _m in (payload or {}).get("messages") or []:
                if _m.get("role") == "system":
                    _parts.append("【system】" + str(_m.get("content") or "")[:400])
                elif _m.get("role") == "user":
                    _parts.append("【user】" + str(_m.get("content") or "")[:400])
            _input = " ".join(_parts)[:2000]
        except Exception:
            pass
        _tool_names = ""
        try:
            _names = []
            for _t in (payload or {}).get("tools") or []:
                _fn = (_t or {}).get("function") or {}
                if _fn.get("name"):
                    _names.append(_fn["name"])
            _tool_names = ",".join(_names)
        except Exception:
            pass
        _temp = (payload or {}).get("temperature", 0) or 0
        _max_tk = int((payload or {}).get("max_tokens", 0) or 0)
        _cost = round(prompt_tk * _COST_INPUT_PER_M / 1e6 + completion_tk * _COST_OUTPUT_PER_M / 1e6, 6)
        with _db_lock:
            conn = _get_conn()
            try:
                conn.execute(
                    "INSERT INTO llm_calls (conversation_id, employee_id, employee_name, stage, model, "
                    "prompt_tokens, completion_tokens, total_tokens, latency_ms, error, "
                    "input, output, temperature, max_tokens, round_no, tool_names, cost, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trace_ctx.get("conversation_id", ""), trace_ctx.get("employee_id", ""),
                     trace_ctx.get("employee_name", ""), trace_ctx.get("stage", ""),
                     model or "", prompt_tk, completion_tk, total_tk, int(latency_s * 1000), error,
                     _input, output, float(_temp), _max_tk, int(round_no or 0), _tool_names, _cost,
                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


def _record_tool_call(trace_ctx, round_no, fn, args, result=None, latency_ms=0, success=True, error=""):
    """将一次 MCP 工具调用（入参/出参/耗时/成败）写入 tool_calls 观测表。"""
    try:
        if not trace_ctx:
            return
        _args = json.dumps(args, ensure_ascii=False)[:500] if args else ""
        _result = ""
        if result is not None:
            try:
                _result = (json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result)[:1000]
            except Exception:
                _result = str(result)[:1000]
        with _db_lock:
            conn = _get_conn()
            try:
                conn.execute(
                    "INSERT INTO tool_calls (conversation_id, employee_id, employee_name, round_no, function_name, "
                    "args, result, latency_ms, success, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (trace_ctx.get("conversation_id", ""), trace_ctx.get("employee_id", ""),
                     trace_ctx.get("employee_name", ""), int(round_no or 0), fn or "",
                     _args, _result, int(latency_ms), 1 if success else 0, error or "",
                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


def _record_rag_retrieval(conversation_id, emp_id, emp_name, query, hits, latency_ms):
    """将一次知识库检索（query/命中数/相似度/来源）写入 rag_retrievals 观测表。"""
    try:
        if not conversation_id:
            return
        scores = []
        sources = []
        for h in hits or []:
            try:
                s = float(h.get("score"))
                scores.append(s)
            except (TypeError, ValueError):
                pass
            src = h.get("source") or h.get("title") or ""
            if src:
                sources.append(src)
        top_score = max(scores) if scores else 0.0
        min_score = min(scores) if scores else 0.0
        with _db_lock:
            conn = _get_conn()
            try:
                conn.execute(
                    "INSERT INTO rag_retrievals (conversation_id, employee_id, employee_name, query, hit_count, "
                    "top_score, min_score, sources, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (conversation_id, emp_id or "", emp_name or "", query or "", len(hits or []),
                     round(top_score, 4), round(min_score, 4),
                     json.dumps(sources, ensure_ascii=False)[:1000], int(latency_ms),
                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


async def deepseek_chat(messages, tools=None, temperature=0.2, max_tokens=4000, model=None, trace_ctx=None, round_no=0):
    """调用 DeepSeek chat completion，支持 function calling。model 默认用 reasoning 模型，可指定 deepseek-chat。
    trace_ctx: 可选观测上下文 dict，如 {"conversation_id", "employee_id", "employee_name", "stage"}，
    传入后成功调用将把 usage/耗时/内容摘要/成本写入 llm_calls 表供监控后台展示。
    round_no: Agent 循环轮次，便于在 Trace 中按轮组织 Span。"""
    key = _load_deepseek_key()
    if not key:
        return {"error": "DeepSeek API Key 未配置"}
    payload = {"model": model or DEEPSEEK_MODEL, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
    _t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code != 200:
                err = f"DeepSeek 调用失败 HTTP {r.status_code}: {r.text[:300]}"
                _record_llm_call(trace_ctx, payload.get("model"), payload, None, time.time() - _t0, error=err, round_no=round_no)
                return {"error": err}
            data = r.json()
        _record_llm_call(trace_ctx, payload.get("model"), payload, data, time.time() - _t0, round_no=round_no)
        return data
    except Exception as _e:
        err = f"DeepSeek 调用异常: {_e}"
        _record_llm_call(trace_ctx, payload.get("model"), payload, None, time.time() - _t0, error=err, round_no=round_no)
        return {"error": err}


# ────────────────────────────────────────────
# 配置驱动：从 DB 动态构建数字员工工具 / 按 MCP Server 路由执行
# ────────────────────────────────────────────

def build_employee_tools(emp_id: str) -> list:
    """从 DB 读取 员工→技能→工具 三级关联，动态生成 OpenAI function schema。
    替代硬编码 BIZ_TOOLS：工具全部来自 mcp_tools 表（含 method/path/params_schema）。"""
    emp = db_get_employee(emp_id)
    if not emp:
        return []
    tools = []
    for mid in emp.get("mcp_tools", []):
        t = db_get_mcp_tool(mid)
        if not t:
            continue
        if not t.get("path"):
            t = dict(t)
            t["path"] = f"/tools/{t['id']}"
        params = t.get("params_schema") or []
        properties, required = {}, []
        for p in params:
            pname = p.get("name")
            if not pname:
                continue
            ptype = "integer" if p.get("type") == "integer" else (
                "number" if p.get("type") in ("number", "float") else "string")
            properties[pname] = {"type": ptype, "description": p.get("desc", "")}
            if p.get("required"):
                required.append(pname)
        tools.append({
            "type": "function",
            "function": {
                "name": t["id"],
                "description": t.get("desc", ""),
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        })
    return tools


async def execute_configured_tool(tool_id: str, args: dict) -> dict:
    """按 mcp_tools 配置的 method/path + 所属 MCP Server 的 base_url 动态执行。
    与 9010 mcp-gateway 协议一致：POST {base}/tools/{name}（或 GET）。

    三路径调度（优先级从高到低）：
      1) base_url = local://python    → 直接调用本地 Python 函数（仅测试/无HTTP网关场景使用）
      2) base_url = http(s)://...     → 通过 HTTP 转发（复用 routes_local_tools / mcp_gateway 的 BaseModel 校验与参数映射）
      3) Server 记录缺失             → 兜底：neuops-local → 9007 HTTP，mcp-gateway → 9010 HTTP
    """
    t = db_get_mcp_tool(tool_id)
    if not t:
        return {"error": f"工具 {tool_id} 不存在"}
    server_id = t.get("server_id") or "neuops-local"
    server = db_get_mcp_server(server_id)
    if not server:
        # Server 缺失兜底：统一走 HTTP 转发（避免因 Server 未注册导致工具完全不可用）
        fallback_base = "http://127.0.0.1:9010" if server_id == "mcp-gateway" else "http://127.0.0.1:9007"
        server = {"id": server_id, "name": server_id, "base_url": fallback_base, "type": "gateway"}
    base = (server.get("base_url") or "").rstrip("/")
    path = t.get("path") or f"/tools/{tool_id}"
    method = (t.get("method") or "POST").upper()

    # ── 仅当显式声明 local://python 协议时走本地函数调用（其他场景走HTTP，复用BaseModel校验/映射）──
    if base == "local://python":
        try:
            from app import mcp_tools as _mt
            fn_map = {
                "table_query": _mt.tool_table_query,
                "table_insert": _mt.tool_table_insert,
                "table_update": _mt.tool_table_update,
                "table_upsert": _mt.tool_table_upsert,
                "send_mail": _mt.tool_send_mail,
                "batch_send_mail": _mt.tool_batch_send_mail,
                "read_inbox_mail": _mt.tool_read_inbox_mail,
                "send_feishu_message": _mt.tool_send_feishu_message,
                "send_feishu_card": _mt.tool_send_feishu_card,
                "procurement_parse_quote": _mt.tool_procurement_parse_quote,
                "procurement_parse_logistics": _mt.tool_procurement_parse_logistics,
                "procurement_create_task": _mt.tool_procurement_create_task,
                "procurement_query_contract": _mt.tool_procurement_query_contract,
                "procurement_query_spare_part": _mt.tool_procurement_query_spare_part,
                "procurement_query_supplier": _mt.tool_procurement_query_supplier,
            }
            fn = fn_map.get(tool_id)
            if not fn:
                return {"error": f"本地工具 {tool_id} 未注册执行函数，请补齐 fn_map"}
            return fn(**args)
        except TypeError as e:
            return {"error": f"调用 {tool_id} 参数不匹配: {e}"}
        except Exception as e:
            return {"error": f"调用本地工具 {tool_id} 失败: {type(e).__name__}: {e}"}

    # ── 网关型工具：走 HTTP 转发 ──
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if method == "GET":
                r = await client.get(url, params=args)
            elif method == "PUT":
                r = await client.put(url, json=args)
            elif method == "PATCH":
                r = await client.patch(url, json=args)
            elif method == "DELETE":
                r = await client.request("DELETE", url, json=args)
            else:
                # POST 默认用 JSON body（兼容 /local/tools/* BaseModel 路由与 mcp-gateway 路由）
                r = await client.post(url, json=args)
            try:
                return r.json()
            except Exception:
                return {"content": r.text[:8000]}
    except Exception as e:
        return {"error": f"调用 {server.get('name', server_id)} 失败: {e}"}


def build_employee_prompt(emp_id: str) -> str:
    """根据员工 DB 记录 + 技能说明 + 工具列表，动态拼接数字员工系统提示词。"""
    emp = db_get_employee(emp_id)
    if not emp:
        return ""
    tools = build_employee_tools(emp_id)
    lines = []
    for i, t in enumerate(tools, 1):
        fn = t["function"]
        name = fn["name"]
        params = fn["parameters"].get("properties", {})
        param_desc = ""
        if params:
            param_desc = "（参数: " + ", ".join(
                f"{k}={v.get('description','')}" for k, v in params.items()) + "）"
        lines.append(f"{i}. {name}：{fn['description']}{param_desc}")
    tool_text = "\n".join(lines) if lines else "（无可用工具）"
    skills = db_list_skills()
    skill_text = "；".join(
        f"{s['name']}:{s.get('desc','')[:50]}" for s in skills if s["id"] in emp.get("skills", []))
    base_prompt = (f"你是「{emp['name']} {emp['id']}」数字员工。{emp.get('desc','')}\n"
                   f"你当前绑定的技能：{skill_text or '无'}\n"
                   f"你有以下原子工具（通过它们查询真实系统的数据，禁止编造数据）：\n{tool_text}\n"
                   f"工作方式：先分析需求 → 选择合适的工具查询真实数据 → 基于返回结果在推理中自行做统计、汇总、对比 → 输出结论。"
                   f"输出要求：用 Markdown 中文输出；涉及表格用 Markdown 表格；金额保留整数加千分位；最后给简要结论。")
    # emp-007 售前投标专家：信息问答 vs 重操作跳转工作台 行为边界（NO-009 FR-7 / NO-006）
    if emp_id == "emp-007":
        base_prompt += (
            "\n\n【工作台协作边界】你是售前投标方案智能组装专家，投标工作台（http://127.0.0.1:9007/bidding）"
            "已支持：项目管理、规范书上传、拆标解析、生成技术方案/点对点应答/PPT大纲/实施方案、合规自检、成果导出。\n"
            "信息类问题（如资质要求有哪些、评分标准解读、中标经验咨询、政策解读）请在聊天内基于绑定知识库直接回答。\n"
            "凡涉及上传规范书、拆标、生成应答、合规自检、导出文档等重操作请求，一律引导用户前往投标工作台 "
            "http://127.0.0.1:9007/bidding 操作，并简要说明页面内已支持的能力，不要在聊天内执行这些重操作。")
    return base_prompt


def build_rag_context(query: str, emp_id: str, top_k: int = 5, conversation_id: str = "", employee_name: str = "") -> str:
    """按员工绑定知识库检索 query，拼装为「参考资料」段落；无命中返回空串。

    有命中时追加到 system prompt，让 DeepSeek 基于真实知识回答并标注来源。
    传入 conversation_id 时顺带把本次检索写入 rag_retrievals 观测表（Trace 展示用）。
    """
    try:
        kb_ids = db_get_employee_kb_ids(emp_id)
        _t0 = time.time()
        hits = search_knowledge(query, kb_ids, top_k=top_k) if kb_ids else []
        if conversation_id:
            _record_rag_retrieval(conversation_id, emp_id, employee_name or emp_id, query, hits,
                                  (time.time() - _t0) * 1000)
    except Exception as e:
        print(f"[agent_chat] RAG 检索失败: {e}")
        hits = []
    if not hits:
        return ""
    lines = ["\n\n【参考资料（来自绑定的知识库，回答时优先采信，并注明 [来源：文件名]）】"]
    for h in hits:
        lines.append(f"- [来源：{h.get('source') or h.get('title') or '未知'}] {h.get('summary') or ''}")
    return "\n".join(lines)


# ── 经营业务数字员工 emp-004 的工具定义（兼容旧逻辑，已由 build_employee_tools 取代）──

BIZ_9006_BASE = "http://127.0.0.1:9006"

BIZ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "列出数据源中所有可查询的原始数据表（表名及版本数）。应先调用它了解有哪些表可用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "获取指定表的结构（所有列名及示例值），了解字段含义后再查询。应先调用它确定要用哪些列。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名，如「总合同表」"},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_table",
            "description": "查询指定数据表的原始明细（原子只读）。支持 columns 列投影（逗号分隔）、keyword 模糊匹配、time_column+start_date/end_date 时间范围过滤。返回 headers 和 rows。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名，如「总合同表」"},
                    "columns": {"type": "string", "description": "要返回的列名，逗号分隔，如「合同编号,合同总金额,统计日期」。留空返回全部列"},
                    "keyword": {"type": "string", "description": "关键词，对任意列模糊匹配，可空"},
                    "time_column": {"type": "string", "description": "时间列名，如「统计日期」，可空"},
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，配合 time_column"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，配合 time_column"},
                    "limit": {"type": "integer", "description": "最多返回行数，默认 100"},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrics",
            "description": "查询 ETL 预计算的指标宽表（如签单毛利率），支持按年份/区域/部门维度过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_key": {"type": "string", "description": "指标任务key，如 gross-margin"},
                    "dim_type": {"type": "string", "description": "维度：year / region / dept，空为全部"},
                },
                "required": ["job_key"],
            },
        },
    },
]

# 主智能体路由工具（从 DB 动态生成，新增员工自动生效）
def build_route_tools() -> list:
    emps = db_list_employees()
    enum = [e["id"] for e in emps]
    desc = "；".join(f"{e['id']}={e['name']}（{e.get('desc','')[:60]}）" for e in emps)
    return [
        {
            "type": "function",
            "function": {
                "name": "route_to_employee",
                "description": "将用户任务路由到对应的数字员工",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "employee": {"type": "string", "enum": enum, "description": desc},
                        "reason": {"type": "string", "description": "一句话路由理由"},
                    },
                    "required": ["employee", "reason"],
                },
            },
        },
    ]


def build_route_system_prompt() -> str:
    emps = db_list_employees()
    lines = "；".join(f"{e['id']} {e['name']}（{e.get('desc','')[:80]}）" for e in emps)
    return ("你是 NeuOps Agent 主智能体（调度中枢）。判断用户需求属于哪类业务，路由到对应数字员工。"
            f"数字员工：{lines}。务必调用 route_to_employee 工具完成路由。")


async def _run_employee_general_loop(employee_id: str, employee_name: str, query: str, history: list,
                                     conversation_id: str, route_reason: str = "",
                                     open_url: str = "http://127.0.0.1:9007"):
    """通用数字员工执行循环（真实执行）：
    基于 build_employee_prompt（DB员工+技能+工具 动态提示词）+ build_employee_tools（DB动态工具）
    + execute_configured_tool（按 mcp_servers 真实转发 9007/9006），最多 15 轮工具调用。"""
    yield sse_event("route", {"employee": employee_id, "name": employee_name, "reason": route_reason or f"{employee_name}任务"})
    yield sse_event("agent_thought", f"✅ 意图识别完成：路由到【{employee_name} {employee_id}】\n理由：{route_reason or f'{employee_name}任务'}")

    emp_system = build_employee_prompt(employee_id) + build_rag_context(query, employee_id,
                                                                        conversation_id=conversation_id,
                                                                        employee_name=employee_name)
    messages = [{"role": "system", "content": emp_system}] + (history or []) + [{"role": "user", "content": query}]
    emp_tools = build_employee_tools(employee_id)
    exec_ctx = {"conversation_id": conversation_id, "stage": "agent_exec",
                "employee_id": employee_id, "employee_name": employee_name}

    for _round in range(15):
        resp = await deepseek_chat(messages, tools=emp_tools, temperature=0.2, max_tokens=8000,
                                   model="deepseek-chat", trace_ctx=exec_ctx, round_no=_round)
        if "error" in resp:
            yield sse_event("agent_thought", f"⚠️ {employee_id} 调用失败：" + str(resp["error"]))
            break
        msg = resp["choices"][0]["message"]
        reasoning = msg.get("reasoning_content", "")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        if reasoning:
            yield sse_event("agent_thought", f"💭 {employee_id} 思考：" + reasoning)
        elif content and tool_calls:
            yield sse_event("agent_thought", f"💭 {employee_id} 计划：" + content)
        if tool_calls:
            messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc["function"]["name"]
                try:
                    fargs = json.loads(tc["function"]["arguments"])
                except Exception:
                    fargs = {}
                yield sse_event("tool_call", {"tool": fn, **fargs})
                _t0 = time.time()
                try:
                    result = await execute_configured_tool(fn, fargs)
                    _record_tool_call(exec_ctx, _round, fn, fargs, result=result,
                                      latency_ms=(time.time() - _t0) * 1000)
                except Exception as _e:
                    _record_tool_call(exec_ctx, _round, fn, fargs, success=False, error=str(_e),
                                      latency_ms=(time.time() - _t0) * 1000)
                    result = {"error": str(_e)}
                yield sse_event("tool_result", _tool_result_summary(fn, result))
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(result, ensure_ascii=False)})
        else:
            if content:
                yield sse_event("agent_message", {"content": content, "actions": [
                    {"id": "open_ops", "label": "🔗 打开监控平台查看详情", "type": "link", "url": open_url}
                ]})
            else:
                yield sse_event("agent_message", {"content": """## ⚠️ 未生成有效结论

模型未返回最终答案，请重试。"""})
            break
    else:
        # 达到轮次上限但未收敛：基于已收集的工具结果输出兜底结论
        yield sse_event("agent_thought", "⚠️ 已进行多轮工具调用，现根据已收集的结果生成最终结论...")
        messages.append({"role": "user", "content": "你已通过多轮工具调用收集了大量数据，但尚未输出最终结论。"
                                                    "现在请不要再调用任何工具，直接基于以上所有工具返回的真实结果，"
                                                    "用 Markdown 中文输出最终分析结论（含数据表格与简短结论）。"})
        try:
            resp = await deepseek_chat(messages, tools=None, temperature=0.2, max_tokens=4000,
                                       model="deepseek-chat",
                                       trace_ctx={"conversation_id": conversation_id, "stage": "agent_exec_fallback",
                                                  "employee_id": employee_id, "employee_name": employee_name},
                                       round_no=_round + 1)
            if "error" not in resp:
                fallback_content = resp["choices"][0]["message"].get("content", "")
                if fallback_content:
                    yield sse_event("agent_message", {"content": fallback_content, "actions": [
                        {"id": "open_ops", "label": "🔗 打开监控平台查看详情", "type": "link", "url": open_url}
                    ]})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已收集多轮工具调用结果，但模型未能整理出最终结论。可查看上方工具调用记录，或简化需求后重试。"""})
            else:
                yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具调用但未收敛，请简化需求重试。"""})
        except Exception as _e:
            yield sse_event("agent_message", {"content": """## ⚠️ 工具调用轮次超限

已完成多轮工具调用但未收敛，请简化需求重试。"""})

    yield sse_event("message_end", {"conversation_id": "conv-demo-001"})


async def execute_biz_tool(name: str, args: dict) -> dict:
    """执行经营业务原子工具，调用 9006 真实接口"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if name == "list_tables":
                r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/tables")
                return r.json()
            if name == "get_table_schema":
                r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/schema", params={
                    "table_name": args.get("table_name", "")})
                return r.json()
            if name == "query_table":
                r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/query", params={
                    "table_name": args.get("table_name", ""),
                    "columns": args.get("columns", ""),
                    "keyword": args.get("keyword", ""),
                    "time_column": args.get("time_column", ""),
                    "start_date": args.get("start_date", ""),
                    "end_date": args.get("end_date", ""),
                    "limit": args.get("limit", 100),
                })
                return r.json()
            if name == "get_metrics":
                r = await client.get(f"{BIZ_9006_BASE}/api/etl/metrics", params={
                    "job_key": args.get("job_key", ""), "dim_type": args.get("dim_type", "")})
                return r.json()
            return {"error": f"未知工具 {name}"}
    except Exception as e:
        return {"error": f"工具执行失败: {e}"}


# ────────────────────────────────────────────
# API 路由
# ────────────────────────────────────────────

@router.post("/api/chat")
async def chat(req: ChatRequest):
    """流式对话接口（模拟 Dify Completion API），会话消息持久化入库"""
    conv_id = req.conversation_id or str(uuid.uuid4())
    # 确保会话存在，并记录用户消息
    ensure_conversation(conv_id, req.query[:20] if req.query else "新对话")
    # 先读历史（在保存当前消息前），这样历史不包含当前这条 query
    history = _load_chat_history(conv_id)
    if not req.approved_action:
        save_user_message(conv_id, req.query)

    async def stream_with_persist():
        thoughts = []
        tools = []
        conclusion = ""
        route = None
        dsh_session_id = ""
        # 引擎分发：req.engine 优先，其次 config.AGENT_ENGINE（默认 legacy）
        engine = (req.engine or AGENT_ENGINE or "legacy").lower()
        if engine == "dsh":
            gen = dsh_agent_run(
                req.query,
                history=history,
                conversation_id=conv_id,
                mode=req.mode,
                selected_skill=req.selected_skill,
            )
        else:
            gen = mock_agent_run(req.query, req.mode, req.selected_skill, req.approved_action, history=history, conversation_id=conv_id)
        async for chunk in gen:
            yield chunk
            # 解析 SSE chunk 收集 agent 消息内容
            evt, data = _parse_sse_chunk(chunk)
            if evt == "agent_thought" and isinstance(data, str):
                thoughts.append(data)
            elif evt == "tool_call" and isinstance(data, dict):
                tools.append({**data, "result": None})
            elif evt == "tool_result" and isinstance(data, dict):
                for t in reversed(tools):
                    if t.get("tool") == data.get("tool") and t.get("result") is None:
                        t["result"] = data
                        break
            elif evt == "agent_message" and isinstance(data, dict):
                conclusion = data.get("content", "")
            elif evt == "route" and isinstance(data, dict):
                route = data
            elif evt == "message_end" and isinstance(data, dict):
                dsh_session_id = data.get("dsh_session_id", "") or ""
        # 流结束后持久化 agent 消息（DSH 引擎附带 engine/dsh_session_id 观测字段）
        save_agent_message(
            conv_id, "\n".join(thoughts), tools, conclusion, route,
            engine=engine if engine == "dsh" else None,
            dsh_session_id=dsh_session_id or None,
        )

    return StreamingResponse(
        stream_with_persist(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


def _parse_sse_chunk(chunk: str):
    """解析单个 SSE 事件块，返回 (event, data)"""
    evt = ""
    data = None
    for line in chunk.strip().split("\n"):
        if line.startswith("event: "):
            evt = line[7:].strip()
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
            except Exception:
                data = None
    return evt, data

