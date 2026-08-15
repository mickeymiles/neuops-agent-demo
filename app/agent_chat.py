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

from .config import BIZ_9006_BASE, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
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
    tool_get_business_metric,
    tool_query_alarm_info,
    tool_query_change_record,
    tool_query_cmdb_topology,
    tool_run_auto_job,
    tool_search_service_log,
)

router = APIRouter()


async def mock_agent_run(query: str, mode: str, selected_skill: str, approved_action: str = None, history: list = None, conversation_id: str = None):
    """模拟 Agent 执行过程，产生 SSE 事件流"""
    
    # 如果是审批确认后的执行
    if approved_action:
        yield sse_event("tool_call", tool_run_auto_job(approved_action, "order-service"))
        yield sse_event("agent_thought", "执行用户审批确认的自动化作业...")
        await asyncio.sleep(1.0)
        yield sse_event("agent_message", {
            "content": f"""## ✅ 自动化作业执行完成

| 项目 | 详情 |
|------|------|
| 作业类型 | {approved_action} |
| 目标服务 | order-service |
| 执行状态 | **成功** |
| 执行耗时 | 4.2s |

**操作结果**：已成功执行 `{approved_action}`，服务容器已重新启动。建议观察 5 分钟确认业务指标恢复正常。

> 如需进一步排查，可输入新指令继续对话。""",
            "actions": []
        })
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

    # ──── 定向技能模式 ────
    if mode == "skill" and selected_skill == "skill-3":
        # 集群巡检 Skill
        yield sse_event("agent_thought", """任务分析：
1. 用户请求生成巡检报告，已选择「业务集群巡检报告生成Skill」
2. 按预设流程执行：采集资源指标 → 查询告警信息 → 检查服务健康 → 汇总生成报告
3. 执行模式：定向技能模式，严格按Skill预设步骤执行""")
        await asyncio.sleep(0.8)
        
        # 步骤1：查询业务指标
        yield sse_event("tool_call", tool_get_business_metric("payment-service"))
        yield sse_event("agent_thought", "步骤1/3：已采集 payment-service 业务指标数据，QPS正常、延迟稳定。")
        await asyncio.sleep(0.6)
        
        # 步骤2：查询告警
        yield sse_event("tool_call", tool_query_alarm_info("payment-service"))
        yield sse_event("agent_thought", "步骤2/3：已获取 payment-service 近期告警，发现1条P2级告警（Redis连接异常）。")
        await asyncio.sleep(0.6)
        
        # 步骤3：查询变更
        yield sse_event("tool_call", tool_query_change_record("payment-service"))
        yield sse_event("agent_thought", "步骤3/3：已拉取近期变更记录，无直接关联的高风险变更。正在汇总生成巡检报告...")
        await asyncio.sleep(1.2)
        
        yield sse_event("agent_message", {
            "content": """## 📊 支付集群今日巡检报告

**巡检时间**：2026-08-07 14:45  
**巡检范围**：payment-service 集群  
**整体评级**：⚠️ 注意（1项需关注）

---

### 一、资源指标概览

| 指标 | 当前值 | 趋势 | 状态 |
|------|--------|------|------|
| QPS | 105 req/s | → 稳定 | ✅ 正常 |
| P99延迟 | 42ms | → 稳定 | ✅ 正常 |
| 错误率 | 0.11% | ↗ 微升 | ✅ 正常 |
| CPU使用率 | 40% | → 稳定 | ✅ 正常 |

### 二、告警信息

| 时间 | 级别 | 标题 | 状态 |
|------|------|------|------|
| 2026-08-06 23:15 | P2-警告 | 支付服务错误率上升（与Redis连接异常相关） | ⚠️ 持续监控 |

### 三、近期变更

- 2026-08-06 22:00：安全组规则更新（prod-payment子网），已执行完毕

### 四、巡检结论

支付集群整体运行稳定，P2级Redis告警已恢复但建议持续观察24小时。无高风险变更在途。

> 📌 建议：将Redis集群健康检查加入每日巡检项。""",
            "actions": []
        })
        yield sse_event("message_end", {"conversation_id": "conv-demo-001"})
        return

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
        yield sse_event("route", {"employee": "emp-004", "name": "经营业务专家", "reason": route_reason or "经营业务类任务"})
        yield sse_event("agent_thought", f"""✅ 意图识别完成：路由到【经营业务专家 emp-004】
理由：{route_reason or '经营业务类任务'}""")

        emp_system = build_employee_prompt("emp-004") + build_rag_context(query, "emp-004", conversation_id=conversation_id, employee_name="经营业务专家")
        messages = [{"role": "system", "content": emp_system}] + (history or []) + [{"role": "user", "content": query}]
        emp_tools = build_employee_tools("emp-004")
        exec_ctx = {"conversation_id": conversation_id, "stage": "agent_exec",
                    "employee_id": "emp-004", "employee_name": "经营业务专家"}

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
                                                      "employee_id": "emp-004", "employee_name": "经营业务专家"},
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

    # ── 路由到研发专家 emp-005（直接修改 9006 系统代码）──
    if employee == "emp-005":
        yield sse_event("route", {"employee": "emp-005", "name": "研发专家", "reason": route_reason or "系统研发类任务"})
        yield sse_event("agent_thought", f"""✅ 意图识别完成：路由到【研发专家 emp-005】
理由：{route_reason or '系统研发类任务'}""")

        emp_system = ("你是「研发专家 emp-005」数字员工，负责按用户需求修改 9006 经营业务展示系统的代码。"
                      "你有以下文件工具，直接读写 9006 项目（/home/ubuntu/contract-compare）的真实代码："
                      "1. list_project_files：列出项目代码文件（backend后端/frontend前端/docs文档），先了解结构；"
                      "2. search_code：按关键词搜索代码内容（query 必填，可加 file_glob 过滤文件名），定位相关逻辑所在文件与行；"
                      "3. read_code_file：读取指定文件内容（带行号，path 相对路径，可用 offset/limit 分页）；"
                      "4. write_new_file：新建文件（path 相对路径 + content 完整内容，仅当文件不存在时可用）；"
                      "5. edit_code_file：局部替换修改（old_string 替换为 new_string，支持模糊匹配容忍空白差异，改前自动备份）；"
                      "6. run_shell：执行白名单验证命令（git status/diff/log 查看改动、pytest 跑测试、ls 看目录）。"
                      "工作方式：先 list_project_files 了解结构 → search_code 定位相关逻辑 → read_code_file 读取相关文件理解现状 → 说明你的改造思路 → edit_code_file 修改（新建用 write_new_file）→ run_shell 验证改动（git diff 看改动、跑测试）→ 总结。"
                      "要求：改动克制，只改必要之处，不重写整个文件；old_string 尽量与原文一致且唯一；"
                      "改完输出改了什么文件、改了什么、为什么这么改，并跑 run_shell 验证改动结果。"
                      "禁止：不越界访问项目目录之外的文件；不编造「已修改」——只有 edit_code_file 返回 success 才算真的改了。") \
                      + build_rag_context(query, "emp-005", conversation_id=conversation_id, employee_name="研发专家")
        messages = [{"role": "system", "content": emp_system}] + (history or []) + [{"role": "user", "content": query}]
        exec_ctx = {"conversation_id": conversation_id, "stage": "agent_exec",
                    "employee_id": "emp-005", "employee_name": "研发专家"}

        for _round in range(20):
            resp = await deepseek_chat(messages, tools=DEV_TOOLS, temperature=0.2, max_tokens=8000, model="deepseek-chat",
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
                        {"id": "open_9006", "label": "🔗 打开9006系统验证改动", "type": "link", "url": "http://127.0.0.1:9006"}
                    ]})
                else:
                    yield sse_event("agent_message", {"content": """## ⚠️ 未生成有效结论

模型未返回最终答案，请重试。"""})
                break
        else:
            # 达到轮次上限但未收敛：追加一次"总结调用"，基于已收集的工具结果输出兜底结论
            yield sse_event("agent_thought", "⚠️ 已进行多轮工具调用，现根据已收集的结果生成最终结论...")
            messages.append({"role": "user", "content": "你已通过多轮工具调用完成了大量代码修改与验证，但尚未输出最终结论。"
                                                        "现在请不要再调用任何工具，直接基于以上所有工具返回的真实结果，"
                                                        "用 Markdown 中文输出最终交付说明：改动了哪些文件、改了什么、是否已通过验证，以及需要注意的事项。"})
            try:
                resp = await deepseek_chat(messages, tools=None, temperature=0.2, max_tokens=4000,
                                           model="deepseek-chat",
                                           trace_ctx={"conversation_id": conversation_id, "stage": "agent_exec_fallback",
                                                      "employee_id": "emp-005", "employee_name": "研发专家"},
                                           round_no=_round + 1)
                if "error" not in resp:
                    fallback_content = resp["choices"][0]["message"].get("content", "")
                    if fallback_content:
                        yield sse_event("agent_message", {"content": fallback_content, "actions": [
                            {"id": "open_9006", "label": "🔗 打开9006系统验证改动", "type": "link", "url": "http://127.0.0.1:9006"}
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

    # ── 路由到运维助手 emp-001（保留原有运维排查流程）──
    yield sse_event("route", {"employee": "emp-001", "name": "运维助手", "reason": route_reason or "运维类任务"})
    yield sse_event("agent_thought", f"""✅ 意图识别完成：路由到【运维助手 emp-001】
理由：{route_reason or '运维类任务'}""")
    yield sse_event("agent_thought", """任务分解：
1. 用户反馈订单服务延迟持续上涨，需要进行全链路排查
2. 匹配可用Skill：服务故障根因分析Skill（skill-1）高度匹配
3. 排查路径：业务指标 → 异常日志 → CMDB拓扑 → 近期变更 → 综合分析
4. 已启用Skills：skill-1, skill-2, skill-3

开始执行多维度排查...""")
    await asyncio.sleep(1.0)

    # 步骤1：查询业务指标
    yield sse_event("tool_call", tool_get_business_metric("order-service"))
    await asyncio.sleep(0.8)
    yield sse_event("agent_thought", """步骤1完成：订单服务指标异常确认
- P99延迟从 45ms → 420ms（30分钟内，增幅 833%）
- 错误率从 0.1% → 4.8%
- CPU使用率 92%，接近瓶颈
→ 确认真实故障，非瞬时抖动，下一步排查日志定位异常原因""")
    await asyncio.sleep(0.6)

    # 步骤2：检索异常日志
    yield sse_event("tool_call", tool_search_service_log("order-service", "ERROR"))
    await asyncio.sleep(0.8)
    yield sse_event("agent_thought", """步骤2完成：日志分析发现关键线索
- 14:32:15 数据库连接超时（db-master:3306）
- 14:32:18 连接池耗尽（active=150/150）
- 14:32:22 熔断器打开（payment-service不可达）
- 14:32:25 慢查询 8.2s
→ 初步判断：数据库连接池是核心瓶颈，引发连锁故障""")
    await asyncio.sleep(0.6)

    # 步骤3：查询CMDB拓扑
    yield sse_event("tool_call", tool_query_cmdb_topology("order-service"))
    await asyncio.sleep(0.8)
    yield sse_event("agent_thought", """步骤3完成：CMDB拓扑分析
- order-service 依赖 payment-service, user-service, inventory-service
- 下游 payment-service 同时出现Redis连接异常告警
- 数据库 db-master.neuops.internal 为单点
→ 依赖链路存在级联风险，需确认变更是否引入""")
    await asyncio.sleep(0.6)

    # 步骤4：查询近期变更
    yield sse_event("tool_call", tool_query_change_record("order-service"))
    await asyncio.sleep(0.8)
    yield sse_event("agent_thought", """步骤4完成：变更关联分析
- CHG-20260807-001（今天10:00）：db-master连接池 max_connections 200→150
  ⚠️ 该变更缩小了连接池上限，与当前连接池耗尽直接相关！
- CHG-20260807-002（今天08:30）：order-service v3.2.1灰度发布（新增批量查询接口）
  新增接口可能增加DB连接需求
→ 根因定位：连接池缩容 + 新接口增加负载 = 连接池耗尽""")
    await asyncio.sleep(1.2)

    # 最终结论
    yield sse_event("agent_message", {
        "content": """## 🔍 订单服务延迟故障根因分析报告

**故障时间**：2026-08-07 14:32 起  
**影响服务**：order-service（核心）→ payment-service（级联）  
**故障等级**：P1-严重

---

### 📌 根因定位

| 层级 | 发现 | 严重度 |
|------|------|--------|
| 🔴 直接原因 | 数据库连接池耗尽（150/150） | 严重 |
| 🟠 触发因素 | 今日 10:00 配置变更：max_connections 200→150 | 高 |
| 🟡 加剧因素 | 今日 08:30 v3.2.1 发布新增批量查询接口，DB连接需求增加 | 中 |
| 🟡 级联影响 | payment-service 熔断（因 order-service 超时请求积压） | 中 |

---

### 🔗 故障时序图

```
10:00  max_connections 200→150 变更执行
       ↓
08:30  v3.2.1 灰度发布（新接口上线）
       ↓
14:32  连接池逐渐饱和 → 连接超时
       ↓
14:32  连接池耗尽，新请求被拒
       ↓
14:32  熔断器触发，payment-service 调用失败
       ↓
14:33  P1 告警触发
```

---

### 💡 建议措施

1. **立即**：回滚 max_connections 配置至 200（或更高）
2. **短期**：审查 v3.2.1 批量查询接口的DB连接使用模式，增加连接复用
3. **长期**：引入连接池动态伸缩策略 + 慢查询监控自动熔断""",
        "actions": [
            {"type": "danger", "id": "restart_service", "label": "🔄 回滚连接池配置（恢复 max_connections=200）", "action": "db_pool_rollback"},
            {"type": "link", "id": "view_metrics", "label": "📊 查看完整指标", "url": "/ops"},
            {"type": "link", "id": "view_topology", "label": "🔗 查看拓扑详情", "url": "/ops#ontology"},
        ]
    })
    
    yield sse_event("message_end", {"conversation_id": "conv-demo-001"})


def sse_event(event: str, data):
    """构造 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════
# DeepSeek 真实 LLM 调用层（真实 AgenticOps）
# ═══════════════════════════════════════════

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"
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
    与 9010 mcp-gateway 协议一致：POST {base}/tools/{name}（或 GET）。"""
    t = db_get_mcp_tool(tool_id)
    if not t or not t.get("server_id"):
        return {"error": f"工具 {tool_id} 不存在或未绑定 MCP Server"}
    server = db_get_mcp_server(t["server_id"])
    if not server:
        return {"error": f"工具 {tool_id} 所属 MCP Server 不存在"}
    base = (server.get("base_url") or "").rstrip("/")
    path = t.get("path") or f"/tools/{tool_id}"
    url = f"{base}{path}"
    method = (t.get("method") or "POST").upper()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if method == "GET":
                r = await client.get(url, params=args)
            else:
                r = await client.post(url, params=args)
            try:
                return r.json()
            except Exception:
                return {"content": r.text[:8000]}
    except Exception as e:
        return {"error": f"调用 {server['name']} 失败: {e}"}


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
    return (f"你是「{emp['name']} {emp['id']}」数字员工。{emp.get('desc','')}\n"
            f"你当前绑定的技能：{skill_text or '无'}\n"
            f"你有以下原子工具（通过它们查询真实系统的数据，禁止编造数据）：\n{tool_text}\n"
            f"工作方式：先分析需求 → 选择合适的工具查询真实数据 → 基于返回结果在推理中自行做统计、汇总、对比 → 输出结论。"
            f"输出要求：用 Markdown 中文输出；涉及表格用 Markdown 表格；金额保留整数加千分位；最后给简要结论。")


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
        async for chunk in mock_agent_run(req.query, req.mode, req.selected_skill, req.approved_action, history=history, conversation_id=conv_id):
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
        # 流结束后持久化 agent 消息
        save_agent_message(conv_id, "\n".join(thoughts), tools, conclusion, route)

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

