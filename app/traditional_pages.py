"""主页面与 /traditional /legacy 传统运维页面路由

2026-08 改造：dashboard/cmdb 使用统一探针真实采集的 ops_entities/ops_metrics/alerts/incidents 数据，
不再使用硬编码假数据。
"""
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from . import db
from . import ops_ontology
from .config import STATIC_DIR

router = APIRouter()

# SVG 线性图标库（与主界面统一风格，24px viewBox / 1.7 stroke / currentColor）
_ICONS = {
    "dashboard": '<path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6" rx="0.5"/><rect x="12" y="8" width="3" height="10" rx="0.5"/><rect x="17" y="5" width="3" height="13" rx="0.5"/>',
    "alarm": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "cmdb": '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    "automation": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "itsm": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h4"/>',
    "unknown": '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r="0.5"/>',
    "warn": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
    "trendUp": '<path d="m3 17 6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
    "trendFlat": '<path d="M3 15h18"/>',
    "trendDn": '<path d="m3 7 6 6 4-4 8 8"/><path d="M14 17h7v-7"/>',
}


def _icon(name, cls="ic"):
    path = _ICONS.get(name, _ICONS["unknown"])
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>')


@router.get("/")
async def index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/health")
async def health():
    return {"status": "ok", "service": "NeuOps Agent Demo"}


def _load_real_dashboard() -> list:
    """从 ops 真实数据生成 dashboard 指标卡"""
    cards = []
    entities = db.ops_get_entities()
    snapshot = db.ops_get_latest_snapshot()
    # 服务器 CPU / 内存 / 磁盘
    for e in entities:
        if e["type"] != "server":
            continue
        m = e.get("metrics", {})
        name = e["name"].split(" ")[0]
        if m.get("cpu_percent") is not None:
            cards.append((f"{name} CPU 使用率", f"{m['cpu_percent']:.1f}%", "trendUp",
                          "实时", "critical" if m['cpu_percent'] >= 90 else "warning" if m['cpu_percent'] >= 80 else ""))
        if m.get("mem_percent") is not None:
            cards.append((f"{name} 内存使用率", f"{m['mem_percent']:.1f}%", "trendFlat",
                          "实时", "critical" if m['mem_percent'] >= 90 else "warning" if m['mem_percent'] >= 80 else ""))
        break  # 仅显示主服务器
    # 磁盘最高占用分区
    max_disk = 0.0
    for e in entities:
        if e["type"] == "server" and "disk_percent" in e.get("metrics", {}):
            max_disk = max(max_disk, float(e["metrics"]["disk_percent"]))
    if max_disk:
        cards.append(("最高磁盘使用率", f"{max_disk:.1f}%", "warn" if max_disk >= 80 else "trendFlat",
                      "实时", "critical" if max_disk >= 90 else "warning" if max_disk >= 80 else ""))
    # 应用健康
    app_up = sum(1 for e in entities if e["type"] == "application" and e["status"] == "running")
    app_down = sum(1 for e in entities if e["type"] == "application" and e["status"] != "running")
    cards.append(("应用健康数", f"{app_up}/{app_up + app_down}", "trendUp" if app_down == 0 else "warn",
                  "running" if app_down == 0 else f"{app_down} 异常", "critical" if app_down else ""))
    # 告警数量
    firing = len([a for a in db._query_rows("SELECT status FROM alerts") if a["status"] == "firing"])
    cards.append(("当前告警", str(firing), "warn" if firing else "trendFlat",
                  "firing" if firing else "无", "critical" if firing else ""))
    return cards if cards else [("暂无数据", "-", "trendFlat", "探针尚未采集", "")]


def _load_real_cmdbs() -> list:
    """从 ops_entities 生成本体资产清单"""
    rows = []
    for e in db.ops_get_entities():
        m = e.get("metrics", {})
        rels = db.ops_get_relations()
        deps = len([r for r in rels if r["source"] == e["id"] or r["target"] == e["id"]])
        rows.append((
            e["name"],
            e["id"],
            ops_ontology.ENTITY_META.get(e["type"], {}).get("label", e["type"]),
            e["status"],
            f"{deps} 关系",
        ))
    return rows if rows else [("暂无数据", "-", "-", "-", "-")]


def _load_real_alarms() -> list:
    """从 alerts 表读取真实告警"""
    rows = []
    for a in db._query_rows("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 20"):
        status_map = {"firing": "active", "resolved": "resolved", "acknowledged": "acknowledged"}
        sev = a.get("severity", "warning")
        level = "P1-严重" if sev == "critical" else "P2-警告" if sev == "warning" else "P3-提示"
        rows.append((level, a.get("message", a.get("rule_name", "")), a.get("created_at", ""), status_map.get(a.get("status"), a.get("status", ""))))
    return rows if rows else [("-", "暂无告警", "-", "resolved")]


@router.get("/traditional/{page}")
async def traditional_page(page: str):
    """返回传统运维页面（dashboard/cmdb 使用真实采集数据）"""
    pages = {
        "dashboard": ("监控大盘", "dashboard", _load_real_dashboard()),
        "alarm": ("告警中心", "alarm", _load_real_alarms()),
        "cmdb": ("CMDB资产平台", "cmdb", _load_real_cmdbs()),
        "automation": ("自动化作业平台", "automation", [
            ("服务重启", "滚动重启指定服务实例", "可用"),
            ("配置变更", "批量修改应用配置文件", "可用"),
            ("灰度发布", "金丝雀发布至指定比例实例", "可用"),
            ("紧急回滚", "回滚至上一个稳定版本", "可用"),
        ]),
        "itsm": ("ITSM工单", "itsm", [
            ("INC-20260807-001", "订单服务延迟排查", "处理中", "P1"),
            ("INC-20260806-002", "Redis集群节点异常", "已解决", "P2"),
            ("CHG-20260807-001", "数据库连接池配置变更", "已完成", "P2"),
            ("INC-20260805-003", "SSL证书即将过期", "待处理", "P3"),
        ]),
    }

    info = pages.get(page, ("未知页面", "unknown", []))
    title, icon_name, items = info
    icon_svg = _icon(icon_name, "ic")

    # 根据页面类型生成不同的卡片布局
    if page == "dashboard":
        cards_html = "".join([
            f"""<div class="metric-card {'c-critical' if item[4]=='critical' else 'c-warning' if item[4]=='warning' else ''}">
                <div class="metric-label">{item[0]}</div>
                <div class="metric-value">{item[1]}</div>
                <div class="metric-trend">{_icon(item[2], 'ic-sm')} {item[3]}</div>
            </div>""" for item in items
        ])
        body = f'<div class="dashboard-grid">{cards_html}</div>'

    elif page == "alarm":
        rows = "".join([
            f"""<tr>
                <td><span class="badge badge-{item[3]}">{item[0]}</span></td>
                <td>{item[1]}</td>
                <td>{item[2]}</td>
                <td><span class="status-{item[3]}">{item[3]}</span></td>
            </tr>""" for item in items
        ])
        body = f"""<div class="table-card"><table class="data-table">
            <thead><tr><th>级别</th><th>告警标题</th><th>触发时间</th><th>状态</th></tr></thead>
            <tbody>{rows}</tbody></table></div>"""

    elif page == "cmdb":
        rows = "".join([
            f"""<tr>
                <td><strong>{item[0]}</strong></td><td>{item[1]}</td><td>{item[2]}</td>
                <td>{item[3]}</td><td>{item[4]}</td>
            </tr>""" for item in items
        ])
        body = f"""<div class="table-card"><table class="data-table">
            <thead><tr><th>应用名称</th><th>应用ID</th><th>类型</th><th>版本</th><th>实例</th></tr></thead>
            <tbody>{rows}</tbody></table></div>"""

    elif page == "automation":
        rows = "".join([
            f"""<tr>
                <td><strong>{item[0]}</strong></td><td>{item[1]}</td>
                <td><span class="badge badge-success">{item[2]}</span></td>
            </tr>""" for item in items
        ])
        body = f"""<div class="table-card"><table class="data-table">
            <thead><tr><th>作业名称</th><th>描述</th><th>状态</th></tr></thead>
            <tbody>{rows}</tbody></table></div>"""

    elif page == "itsm":
        rows = "".join([
            f"""<tr>
                <td><strong>{item[0]}</strong></td><td>{item[1]}</td>
                <td><span class="badge badge-{'active' if item[2]=='处理中' else 'success' if item[2]=='已完成' else 'warning'}">{item[2]}</span></td>
                <td><span class="badge badge-{'critical' if item[3]=='P1' else ''}">{item[3]}</span></td>
            </tr>""" for item in items
        ])
        body = f"""<div class="table-card"><table class="data-table">
            <thead><tr><th>工单编号</th><th>标题</th><th>状态</th><th>优先级</th></tr></thead>
            <tbody>{rows}</tbody></table></div>"""

    else:
        body = "<p class=\"empty\">页面不存在</p>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - NeuOps 传统运维平台</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', sans-serif;
  background:
    radial-gradient(1100px 500px at 85% -10%, rgba(14,165,233,.10), transparent 60%),
    radial-gradient(800px 450px at -10% 110%, rgba(99,102,241,.10), transparent 55%),
    #0B1220;
  background-attachment: fixed;
  color: #E2E8F0;
  min-height: 100vh;
}}
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-thumb {{ background: #27334B; border-radius: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
.header {{
  background: linear-gradient(90deg, rgba(15,23,42,.9), rgba(13,20,36,.9));
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #1E2A44;
  color: #F8FAFC;
  padding: 16px 28px;
  display: flex; align-items: center; gap: 12px;
  font-size: 18px; font-weight: 600;
  box-shadow: 0 2px 16px rgba(0,0,0,.3);
  position: sticky; top: 0; z-index: 10;
}}
.header .ic {{ width: 22px; height: 22px; color: #38BDF8; }}
.header .sub {{ font-size: 12px; color: #64748B; font-weight: 400; margin-left: 8px; }}
.container {{ max-width: 1200px; margin: 28px auto; padding: 0 28px; }}
.dashboard-grid {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(240px,1fr)); gap: 16px; }}
.metric-card {{
  background: linear-gradient(180deg, #111A2E 0%, #0E1626 100%);
  border: 1px solid #1E2A44;
  border-left: 3px solid #38BDF8;
  border-radius: 12px; padding: 22px;
  box-shadow: 0 4px 20px rgba(0,0,0,.25);
  transition: transform .18s ease, border-color .18s ease;
}}
.metric-card:hover {{ transform: translateY(-2px); border-color: rgba(56,189,248,.4); }}
.metric-card.c-critical {{ border-left-color: #EF4444; }}
.metric-card.c-warning {{ border-left-color: #F59E0B; }}
.metric-label {{ font-size: 13px; color: #94A3B8; margin-bottom: 10px; }}
.metric-value {{ font-size: 30px; font-weight: 700; color: #F8FAFC; margin-bottom: 6px; font-variant-numeric: tabular-nums; }}
.metric-trend {{ font-size: 13px; color: #10B981; display: flex; align-items: center; gap: 4px; }}
.metric-trend .ic-sm {{ width: 14px; height: 14px; }}
.c-critical .metric-trend {{ color: #EF4444; }}
.c-warning .metric-trend {{ color: #F59E0B; }}
.table-card {{
  background: linear-gradient(180deg, #111A2E 0%, #0E1626 100%);
  border: 1px solid #1E2A44; border-radius: 12px; overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,.25);
}}
.data-table {{ width: 100%; border-collapse: collapse; }}
.data-table th {{
  background: #0E1626; padding: 14px 18px; text-align: left;
  font-size: 13px; color: #94A3B8; font-weight: 500;
  border-bottom: 1px solid #1E2A44; letter-spacing: .3px;
}}
.data-table td {{ padding: 14px 18px; border-bottom: 1px solid #16203A; font-size: 14px; }}
.data-table tbody tr:hover {{ background: rgba(56,189,248,.05); }}
.data-table tbody tr:last-child td {{ border-bottom: none; }}
.badge {{ padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 500; border: 1px solid transparent; }}
.badge-active {{ background: rgba(245,63,63,.12); color: #F87171; border-color: rgba(245,63,63,.3); }}
.badge-success {{ background: rgba(16,185,129,.12); color: #34D399; border-color: rgba(16,185,129,.3); }}
.badge-critical {{ background: rgba(239,68,68,.14); color: #F87171; border-color: rgba(239,68,68,.35); }}
.badge-warning {{ background: rgba(245,158,11,.12); color: #FBBF24; border-color: rgba(245,158,11,.3); }}
.status-active {{ color: #F87171; font-weight: 500; }}
.status-acknowledged {{ color: #FBBF24; }}
.status-resolved {{ color: #34D399; }}
.empty {{ color: #64748B; text-align: center; padding: 60px 0; font-size: 14px; }}
</style>
</head>
<body>
<div class="header">{icon_svg} {title}<span class="sub">AI 智能体运维工作台 · 传统运维入口</span></div>
<div class="container">{body}</div>
</body>
</html>"""
    return HTMLResponse(html)


# ────────────────────────────────────────────
# /legacy/* 别名路由（兼容前端链接）
# ────────────────────────────────────────────

_LEGACY_MAP = {
    "monitor": "dashboard",
    "alarm": "alarm",
    "cmdb": "cmdb",
    "auto": "automation",
    "itsm": "itsm",
}

@router.get("/legacy/{page}")
async def legacy_page(page: str):
    """/legacy/* 别名 → /traditional/*"""
    mapped = _LEGACY_MAP.get(page, page)
    return await traditional_page(mapped)
