#!/usr/bin/env python3
"""从 index.html 提取后台管理（/manage）所需 JS 符号，生成 static/manage.app.js。

仅做只读提取 + 组装，不修改 index.html。
用法: python3 scripts/build_manage_js.py
"""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(BASE, "static", "index.html")
OUT = os.path.join(BASE, "static", "manage.app.js")

src = open(INDEX, encoding="utf-8").read()
m = re.search(r"<script>(.*)</script>", src, re.S)
if not m:
    raise SystemExit("index.html 中未找到 <script> 块")
js = m.group(1)


def find_balanced(code, start, oc, cc):
    """从 start 处（oc 位置）开始，找到与 oc 配对的 cc 结束位置（含）。"""
    depth = 0
    i = start
    in_str = None
    while i < len(code):
        c = code[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in "'\"`":
                in_str = c
            elif c == oc:
                depth += 1
            elif c == cc:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def extract_decl(name):
    esc = re.escape(name)
    pats = [
        (r"^const\s+" + esc + r"\s*=\s*\{", "{", "}"),
        (r"^const\s+" + esc + r"\s*=\s*\[", "[", "]"),
        (r"^(?:let|var|const)\s+" + esc + r"\s*=", None, None),
        (r"^(?:async\s+)?function\s+" + esc + r"\s*\(", "{", "}"),
    ]
    for pat, oc, cc in pats:
        mm = re.search(pat, js, re.M)
        if not mm:
            continue
        if oc is None:
            semi = js.find(";", mm.end())
            return js[mm.start():semi + 1]
        oi = js.find(oc, mm.end())
        end = find_balanced(js, oi, oc, cc)
        if end == -1:
            continue
        # 仅当 } 后紧跟空白再加分号（对象/变量声明的结尾）时才吞掉分号，
        # 避免把后续函数定义的开头误并入（如 showEmpList 后紧跟 showEmpDetail）。
        semi = js.find(";", end)
        if semi != -1 and js[end + 1:semi].strip() == "":
            return js[mm.start():semi + 1]
        return js[mm.start():end + 1]
    return None


# 需要提取的顶层符号（const 对象 / 状态变量 / 函数）
WANTED = [
    "ICONS", "UI_DIALOG_ICONS",
    "SERVER_EDIT_ID", "SKILL_EDIT_ID", "SKILL_DETAIL_ID", "S_TOOLS",
    "kbKBS", "kbEMPS", "kbCUR", "kbCUR_PAGE", "kbPAGE_SIZE", "kbBIND_KB_ID",
    "kb$", "toastTimer",
    "escapeHtml", "icon", "showToast", "uiAlert", "uiConfirm",
    "openUiDialog", "closeUiDialog",
    "renderEmployees", "showEmpList", "openCreateEmp", "closeCreateEmp",
    "doCreateEmployee", "deleteEmployee",
    "renderEmpSkillTab", "toggleEmpSkill", "renderEmpMcpTab",
    "filterEmpMcpTools", "renderEmpSettingsTab", "saveEmpSettings",
    "openAddSkill", "closeAddSkill", "loadAddSkillList", "confirmAddSkill",
    "renderSkillsPage", "searchSkills", "switchSkillTab",
    "openCreateSkill", "closeCreateSkill", "openEditSkill",
    "loadSkillToolOptions", "doCreateSkill", "deleteSkill",
    "showSkillDetail", "closeSkillDetail",
    "renderToolsPage", "openServerModal", "closeServerModal",
    "doSaveServer", "syncServerTools", "deleteServer",
    "kbApi", "kbLoad", "kbRenderList", "kbOpenDetail", "kbShowList",
    "kbLoadChunks", "kbGoPage", "kbDeleteChunk", "kbRebuildIndex",
    "kbDeleteBase", "kbOpenUpload", "kbCloseUpload", "kbSetupDrop",
    "kbHandleFiles", "kbOpenBind", "kbCloseBind", "kbSubmitBind",
    "kbOpenCreate", "kbCloseCreate", "kbSubmitCreate",
]

parts = []
missing = []
for name in WANTED:
    seg = extract_decl(name)
    if seg is None:
        missing.append(name)
        continue
    parts.append(seg)

if missing:
    print("MISSING:", ", ".join(missing))

# ── manage 专属代码（不来自 index.html） ──
manage_js = r"""
// ═══════════ MANAGE PAGE LOGIC ═══════════
const BIZ_9006_BASE = document.getElementById('app-root')?.dataset?.biz9006 || '/';

// 后台管理页面切换
function navigateTo(page) {
  const map = {
    work: 'page-work',
    knowledge: 'page-knowledge',
    tools: 'page-tools',
    skills: 'page-skills',
    employees: 'page-employees',
  };
  const target = map[page] || 'page-work';
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  const el = document.getElementById(target);
  if (el) el.classList.remove('hidden');
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === page);
  });
  // 懒加载各页数据
  if (page === 'skills') renderSkillsPage();
  if (page === 'tools') renderToolsPage();
  if (page === 'knowledge') kbLoad();
  if (page === 'employees') renderEmployees('');
}

// 工作成果：业务数据平台（9006 真实入口，单张大卡片 + 实时概要指标）
function renderWork() {
  const grid = document.getElementById('workCardGrid');
  if (!grid) return;
  const base = BIZ_9006_BASE;
  grid.innerHTML = `
    <a class="work-card work-card-hero" href="${base}/" target="_blank" rel="noopener">
      <div class="work-hero-head">
        <div class="work-card-icon">${icon('chart')}</div>
        <div class="work-hero-titles">
          <div class="work-card-title">业务数据平台</div>
          <div class="work-card-desc">运营管理一站式工作台：合同比对 / 回款周期 / 资金占用 / 毛利分析</div>
        </div>
        <div class="work-card-open">打开平台 <span>↗</span></div>
      </div>
      <div class="work-metrics" id="workMetrics">
        <div class="work-metrics-loading">正在连接业务平台获取概要数据…</div>
      </div>
    </a>`;
  loadWorkMetrics(base);
}

function fmtWan(v) {
  if (v === undefined || v === null || v === '' || v === '-') return '—';
  const n = typeof v === 'string' ? parseFloat(String(v).replace(/[,¥元]/g, '')) : v;
  if (!isFinite(n)) return String(v);
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(2) + ' 万';
  return n.toLocaleString('zh-CN');
}

function fmtNum(v) {
  if (v === undefined || v === null || v === '' || v === '-') return '—';
  const n = typeof v === 'string' ? parseFloat(String(v).replace(/[,¥元]/g, '')) : v;
  if (!isFinite(n)) return String(v);
  return n.toLocaleString('zh-CN');
}

async function loadWorkMetrics(base) {
  const box = document.getElementById('workMetrics');
  if (!box) return;
  const get = async (u) => {
    const r = await fetch(base + u);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  try {
    const [contracts, gross, pay, fund] = await Promise.allSettled([
      get('/api/contracts'),
      get('/api/gross/metrics'),
      get('/api/payment-cycle/metrics'),
      get('/api/fund/metrics'),
    ]);
    const stats = contracts.status === 'fulfilled' ? contracts.value.stats || {} : {};
    const grossSum = gross.status === 'fulfilled' ? gross.value.summary || {} : {};
    const paySum = pay.status === 'fulfilled' && pay.value.data ? pay.value.data.summary || {} : {};
    const fundSum = fund.status === 'fulfilled' && fund.value.data ? fund.value.data.summary || {} : {};
    const items = [
      { label: '合同总数', value: fmtNum(stats.total) + ' 个', icon: 'clipboard' },
      { label: '合同总额', value: fmtWan(stats.total_amount), icon: 'chart' },
      { label: '2026签单毛利率', value: grossSum['2026签单毛利率'] || '—', icon: 'activity' },
      { label: '平均回款周期', value: paySum['平均回款周期'] || '—', icon: 'clock' },
      { label: '当前资金占用', value: fmtWan(fundSum['当前资金占用总额']), icon: 'folder' },
      { label: '净现金流', value: fmtWan(fundSum['净现金流总额']), icon: 'doc' },
    ];
    const ok = items.some(i => i.value !== '—' && i.label !== '…');
    if (!ok) throw new Error('no data');
    box.innerHTML = items.map(i => `
      <div class="work-metric">
        <div class="work-metric-ic">${icon(i.icon)}</div>
        <div class="work-metric-val">${escapeHtml(i.value)}</div>
        <div class="work-metric-label">${escapeHtml(i.label)}</div>
      </div>`).join('');
  } catch (e) {
    box.innerHTML = `<div class="work-metrics-err">概要数据暂不可用，点击卡片直接进入平台</div>`;
  }
}

// 数字员工详情（manage 版：技能 / MCP / 设置 三个 tab，无会话）
async function showEmpDetail(id) {
  const listEl = document.getElementById('empListView');
  const detailEl = document.getElementById('empDetailView');
  if (listEl) listEl.classList.add('hidden');
  if (detailEl) detailEl.classList.remove('hidden');
  window.__curEmp = { emp_id: id, display_name: '', emp_type: '', name: '' };
  try {
    const r = await fetch('/api/employees/' + id + '/full').then(x => x.json());
    if (r.error) { uiAlert({ title: '加载失败', message: r.error }); return; }
    window.__curEmp = r;
    renderEmpDetailTop(r);
    window.__empTab = 'skill';
    renderEmpSkillTab(r);
  } catch (e) {
    console.error(e);
    uiAlert({ title: '加载失败', message: '无法加载员工详情' });
  }
}

function renderEmpDetailTop(emp) {
  const top = document.getElementById('empDetailTop');
  const curTab = (window.__empTab || 'skill');
  top.innerHTML = `
    <div class="emp-detail-bar">
      <span class="emp-back" onclick="showEmpList()">← 返回列表</span>
      <div class="emp-detail-title">
        <span class="emp-avatar" style="background:linear-gradient(135deg,#4F8CFF,#22D3EE);">${escapeHtml((emp.display_name || emp.name || 'E')[0])}</span>
        <div>
          <div class="emp-detail-name">${escapeHtml(emp.display_name || emp.name || emp.emp_id)}</div>
          <div class="emp-detail-meta">${escapeHtml(emp.emp_type || '通用')} · ${escapeHtml(emp.emp_id || '')}</div>
        </div>
      </div>
      <div class="emp-detail-tabs">
        <button class="emp-detail-tab ${curTab === 'skill' ? 'active' : ''}" onclick="window.__empTab='skill';renderEmpDetailTop(window.__curEmp);renderEmpSkillTab()">技能</button>
        <button class="emp-detail-tab ${curTab === 'mcp' ? 'active' : ''}" onclick="window.__empTab='mcp';renderEmpDetailTop(window.__curEmp);renderEmpMcpTab()">MCP 服务</button>
        <button class="emp-detail-tab ${curTab === 'settings' ? 'active' : ''}" onclick="window.__empTab='settings';renderEmpDetailTop(window.__curEmp);renderEmpSettingsTab()">设置</button>
      </div>
    </div>`;
  ['emp-tab-skill', 'emp-tab-mcp', 'emp-tab-settings', 'emp-tab-conv'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  });
  const active = document.getElementById('emp-tab-' + curTab);
  if (active) active.classList.remove('hidden');
}

function init() {
  renderWork();
  navigateTo('work');
}
document.addEventListener('DOMContentLoaded', init);
"""

out = "\n\n".join(parts) + "\n" + manage_js
with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)

print(f"OK: {OUT}  ({len(out)} bytes)")
print(f"extracted {len(parts)}/{len(WANTED)} symbols")
