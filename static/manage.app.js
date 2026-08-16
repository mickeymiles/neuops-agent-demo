const ICONS = {
  bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  robot: '<rect x="4" y="8" width="16" height="12" rx="2"/><circle cx="9" cy="14" r="1.4"/><circle cx="15" cy="14" r="1.4"/><path d="M12 8V5M9 3h6"/><path d="M4 13H2M22 13h-2"/>',
  puzzle: '<path d="M10 3v2a2 2 0 0 1-4 0V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1zM4 7h4v3H6a1 1 0 0 0-1 1v1h3v4H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zM12 7h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-5v-4h-2a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  chart: '<path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6" rx="0.5"/><rect x="12" y="8" width="3" height="10" rx="0.5"/><rect x="17" y="5" width="3" height="13" rx="0.5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  brain: '<path d="M9.5 2A2.5 2.5 0 0 0 7 4.5v.55A3.5 3.5 0 0 0 4 8.5c0 .64.17 1.24.47 1.75A3.5 3.5 0 0 0 3 13.5c0 .64.17 1.24.47 1.75A3.5 3.5 0 0 0 7 18.95v.55a2.5 2.5 0 0 0 5 0V4.5A2.5 2.5 0 0 0 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 1 17 4.5v.55A3.5 3.5 0 0 1 20 8.5c0 .64-.17 1.24-.47 1.75A3.5 3.5 0 0 1 21 13.5c0 .64-.17 1.24-.47 1.75A3.5 3.5 0 0 1 17 18.95v.55a2.5 2.5 0 0 1-5 0V4.5A2.5 2.5 0 0 1 14.5 2z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r="0.5"/>',
  paperclip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  chevronLeft: '<path d="m15 18-6-6 6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  warn: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  refresh: '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  play: '<path d="m5 3 14 9-14 9V3z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  pin: '<path d="M12 17v5"/><path d="M9 3h6l1 7-2 3H10l-2-3 1-7zM12 3v2"/>',
  unpin: '<path d="M12 17v5"/><path d="M9.4 3h5.2l1 7-2 3H10.4l-1-7z"/><path d="m4 4 16 16"/><path d="M12 3v2"/>',
  share: '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="m16 6-4-4-4 4M12 2v13"/>',
  edit: '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
  folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  folderMove: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><path d="M9 13l-2 2 2 2M7 15h7"/>',
  moreH: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
};
function icon(name, cls) {
  const ic = ICONS[name] || ICONS.help;
  return `<svg class="svg-icon ${cls || ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ic}</svg>`;
}

const UI_DIALOG_ICONS = {
  info: '<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
  success: '<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m22 4-10 10.01-3-3"/></svg>',
  error: '<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/></svg>',
  warning: '<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
  confirm: '<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>'
};
let uiDialogCallback = null;
let uiDialogIsConfirm = false;

function openUiDialog(opts) {
  // opts: { type, title, message, okText, cancelText, danger }
  const mask = document.getElementById('uiDialogMask');
  const icon = document.getElementById('uiDialogIcon');
  const msg = document.getElementById('uiDialogMsg');
  const okBtn = document.getElementById('uiDialogOkBtn');
  const cancelBtn = document.getElementById('uiDialogCancelBtn');
  const type = opts.type || 'info';
  uiDialogIsConfirm = !!(opts.cancelText);
  icon.className = 'ui-dialog-icon type-' + type;
  icon.innerHTML = UI_DIALOG_ICONS[type] || UI_DIALOG_ICONS.info;
  document.getElementById('uiDialogTitle').textContent = opts.title || (type === 'confirm' ? '操作确认' : '提示');
  msg.textContent = opts.message || '';
  okBtn.textContent = opts.okText || (uiDialogIsConfirm ? '确定' : '知道了');
  okBtn.className = 'btn-confirm ' + (opts.danger ? 'danger' : 'primary');
  if (uiDialogIsConfirm) {
    cancelBtn.textContent = opts.cancelText || '取消';
    cancelBtn.classList.remove('hidden');
  } else {
    cancelBtn.classList.add('hidden');
  }
  mask.classList.remove('hidden');
  setTimeout(() => okBtn.focus(), 80);
}

let SERVER_EDIT_ID = null;

let TOOL_GROUP_EDIT_ID = null;

let SKILL_EDIT_ID = null;

let SKILL_DETAIL_ID = null;

let S_TOOLS = { servers: [], tools: [] };

// 工具中心：左侧树选中范围（all=全部工具 / group=业务分组 / server=分组下某 Server）
const TOOL_SEL = { type: 'all', group: '', serverId: '', serverName: '' };
let TOOL_DETAIL_ID = null;

// 管理端全局状态（独立定义，不依赖 index.html 的 S）
const S = {
  employees: [],
  empDetail: null,
  skills: [],
  currentSkillTab: 'market',
  skillKeyword: '',
};

let kbKBS = [], kbEMPS = [], kbCUR = null, kbCUR_PAGE = 0;

const kbPAGE_SIZE = 20;

let kbBIND_KB_ID = null;

const kb$ = id => document.getElementById(id);

let toastTimer = null;

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function icon(name, cls) {
  const ic = ICONS[name] || ICONS.help;
  return `<svg class="svg-icon ${cls || ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ic}</svg>`;
}

function showToast(msg, isErr) {
  const t = document.getElementById('appToast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'show' + (isErr ? ' toast-danger' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, 2400);
}

function uiAlert(opts) {
  // 兼容两种用法: uiAlert('消息') 或 uiAlert({title, message, type})
  if (typeof opts === 'string') opts = { message: opts };
  return new Promise(resolve => {
    uiDialogCallback = () => resolve(true);
    openUiDialog(Object.assign({ type: 'info', okText: '知道了' }, opts));
  });
}

function uiConfirm(opts) {
  // 兼容两种用法: uiConfirm('消息') 或 uiConfirm({title, message, danger, okText, cancelText})
  if (typeof opts === 'string') opts = { message: opts };
  return new Promise(resolve => {
    uiDialogCallback = ok => resolve(!!ok);
    openUiDialog(Object.assign({ type: 'confirm', okText: '确定', cancelText: '取消', danger: true }, opts));
  });
}

function openUiDialog(opts) {
  // opts: { type, title, message, okText, cancelText, danger }
  const mask = document.getElementById('uiDialogMask');
  const icon = document.getElementById('uiDialogIcon');
  const msg = document.getElementById('uiDialogMsg');
  const okBtn = document.getElementById('uiDialogOkBtn');
  const cancelBtn = document.getElementById('uiDialogCancelBtn');
  const type = opts.type || 'info';
  uiDialogIsConfirm = !!(opts.cancelText);
  icon.className = 'ui-dialog-icon type-' + type;
  icon.innerHTML = UI_DIALOG_ICONS[type] || UI_DIALOG_ICONS.info;
  document.getElementById('uiDialogTitle').textContent = opts.title || (type === 'confirm' ? '操作确认' : '提示');
  msg.textContent = opts.message || '';
  okBtn.textContent = opts.okText || (uiDialogIsConfirm ? '确定' : '知道了');
  okBtn.className = 'btn-confirm ' + (opts.danger ? 'danger' : 'primary');
  if (uiDialogIsConfirm) {
    cancelBtn.textContent = opts.cancelText || '取消';
    cancelBtn.classList.remove('hidden');
  } else {
    cancelBtn.classList.add('hidden');
  }
  mask.classList.remove('hidden');
  setTimeout(() => okBtn.focus(), 80);
}

function closeUiDialog(result) {
  const mask = document.getElementById('uiDialogMask');
  const cb = uiDialogCallback;
  uiDialogCallback = null;
  mask.classList.add('hidden');
  if (typeof cb === 'function') cb(result);
}

async function renderEmployees(keyword) {
  const kw = (keyword || '').toLowerCase();
  try {
    const r = await fetch('/api/employees').then(x => x.json());
    S.employees = r.employees || [];
    const list = S.employees.filter(e => !kw || e.name.toLowerCase().includes(kw) || (e.desc || '').toLowerCase().includes(kw));
    const tbody = document.querySelector('#empTable tbody');
    tbody.innerHTML = list.map(e => `
      <tr>
        <td>${e.id}</td>
        <td>${e.name}</td>
        <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.desc || '-'}</td>
        <td>${e.type || '-'}</td>
        <td>${e.created || '-'}</td>
        <td class="table-actions">
          <button class="tb-btn" title="查看详情" onclick="showEmpDetail('${e.id}')">${icon('eye')}</button>
          <button class="tb-btn danger" title="删除" onclick="deleteEmployee('${e.id}')">${icon('trash')}</button>
        </td>
      </tr>`).join('');
  } catch (e) { console.error(e); }
}

function showEmpList() {
  document.getElementById('empListView').classList.remove('hidden');
  document.getElementById('empDetailView').classList.add('hidden');
}

function openCreateEmp() { document.getElementById('createEmpModal').classList.remove('hidden'); }

function closeCreateEmp() { document.getElementById('createEmpModal').classList.add('hidden'); }

async function doCreateEmployee() {
  const name = document.getElementById('empFormName').value.trim();
  if (!name) { uiAlert({ title: '提示', message: '请输入员工名称', type: 'warning' }); return; }
  const body = {
    name,
    desc: document.getElementById('empFormDesc').value.trim(),
    type: document.getElementById('empFormType').value,
    prompt: document.getElementById('empFormPrompt').value.trim(),
  };
  try {
    await fetch('/api/employees', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    closeCreateEmp();
    document.getElementById('empFormName').value = '';
    document.getElementById('empFormDesc').value = '';
    document.getElementById('empFormPrompt').value = '';
    renderEmployees();
  } catch (e) { uiAlert({ title: '创建失败', message: e.message, type: 'error' }); }
}

async function deleteEmployee(id) {
  if (!await uiConfirm({ title: '删除员工', message: '确认删除该数字员工？', danger: true })) return;
  await fetch('/api/employees/' + id, { method: 'DELETE' });
  renderEmployees();
}

async function renderEmpSkillTab(emp) {
  emp = emp || window.__curEmp || S.empDetail;
  if (!emp) return;
  const bound = new Set(emp.skills || []);
  const wrap = document.getElementById('emp-tab-skill');
  wrap.innerHTML = `
    <div class="emp-detail-body">
      <div class="skill-mgr-bar">
        <div class="skill-filter-tabs"><span class="skill-filter-tab active">全部</span></div>
      </div>
      <div class="emp-pool-hint">数字员工通过「技能」获得能力：选择使用的技能后，其绑定的 MCP 工具将自动生效。点击技能卡片可查看详情。</div>
      <div class="skill-mgr-cards" id="empSkillPool"></div>
    </div>`;
  try {
    const r = await fetch('/api/skills').then(x => x.json());
    const skills = r.skills || [];
    document.getElementById('empSkillPool').innerHTML = skills.length ? skills.map(s => {
      const active = bound.has(s.id);
      return `
      <div class="skill-mgr-card emp-select-card" style="cursor:pointer;" onclick="showSkillDetail('${s.id}')">
        <div class="card-top">
          <h4>${s.name}${s.category === 'custom' ? '<span class="tag" style="margin-left:6px;color:var(--c-primary);border-color:rgba(56,189,248,.4)">自定义</span>' : ''}</h4>
          <label class="skill-switch" title="${active ? '点击停用' : '点击使用'}" onclick="event.stopPropagation()">
            <input type="checkbox" ${active ? 'checked' : ''} onchange="toggleEmpSkill('${s.id}')">
            <span class="slider"></span>
          </label>
        </div>
        <div class="card-eng">${s.id}</div>
        <div class="card-desc">${s.desc || ''}</div>
        <div class="card-update" style="display:flex;align-items:center;justify-content:space-between;">
          <span>分类：${s.category || '-'}</span>
          <span style="font-size:12px;color:${active ? 'var(--c-primary)' : 'var(--c-text-time)'};">${active ? '使用中' : '未使用'}</span>
        </div>
      </div>`;
    }).join('') : '<div class="todo-empty" style="grid-column:1/-1;border:1px dashed var(--c-border-light);border-radius:8px;text-align:center;color:var(--c-text-time);padding:24px;">后台能力池暂无技能，请到「技能中心」配置</div>';
  } catch (e) {
    document.getElementById('empSkillPool').innerHTML = '<div class="todo-empty" style="grid-column:1/-1;color:var(--c-danger);">技能加载失败：' + e.message + '</div>';
  }
}

async function toggleEmpSkill(skillId) {
  const emp = window.__curEmp || S.empDetail;
  if (!emp) return;
  const cur = new Set(emp.skills || []);
  const willUse = !cur.has(skillId);
  if (willUse) cur.add(skillId); else cur.delete(skillId);
  try {
    const r = await fetch('/api/employees/' + emp.id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skills: [...cur] })
    });
    const res = await r.json();
    if (!r.ok || res.error) { showToast(res.error || '操作失败', true); renderEmpSkillTab(emp); return; }
    showToast(willUse ? '技能已启用，对应 MCP 工具已生效' : '技能已停用，对应 MCP 工具已移除');
    emp.skills = [...cur];
    if (window.__curEmp && window.__curEmp !== emp) window.__curEmp.skills = [...cur];
    if (S.empDetail && S.empDetail !== emp && S.empDetail !== window.__curEmp) S.empDetail.skills = [...cur];
    renderEmpSkillTab(emp);
  } catch (e) { showToast('操作失败：' + e.message, true); renderEmpSkillTab(emp); }
}

async function renderEmpMcpTab(emp) {
  emp = emp || window.__curEmp || S.empDetail;
  if (!emp) return;
  const tools = emp.mcp_detail || [];
  const wrap = document.getElementById('emp-tab-mcp');
  wrap.innerHTML = `
    <div class="emp-detail-body">
      <div class="mcp-header-row">
        <div><span class="mcp-title">MCP 工具服务</span><span class="mcp-count">由已启用技能自动推导 · 只读</span></div>
        <div class="mcp-right">
          <input type="text" id="mcpToolSearch" placeholder="搜索工具..." oninput="filterEmpMcpTools(this.value)">
        </div>
      </div>
      <div class="emp-pool-hint">该数字员工启用的技能共绑定以下 MCP 工具。工具能力由「技能」决定，如需调整请到「技能」页使用/停用对应技能。</div>
      <div id="empMcpPool" style="display:flex;flex-direction:column;gap:8px;"></div>
    </div>`;
  document.getElementById('empMcpPool').innerHTML = tools.length ? tools.map(t => `
      <div class="tool-card-detail mcp-tool-row" style="display:flex;align-items:center;gap:10px;">
        <div class="tool-info">
          <span class="tool-id">${t.name}</span>
          <span class="tool-desc-cn">${t.desc || ''}</span>
        </div>
        <span class="tool-tag" style="margin-left:auto;color:var(--c-text-time);">来自技能</span>
      </div>`).join('') : '<div class="todo-empty" style="border:1px dashed var(--c-border-light);border-radius:8px;text-align:center;color:var(--c-text-time);padding:24px;">该数字员工暂无可用工具，请到「技能」页启用对应技能</div>';
}

function filterEmpMcpTools(val) {
  const kw = (val || '').toLowerCase();
  document.querySelectorAll('.mcp-tool-row').forEach(row => {
    const txt = (row.textContent || '').toLowerCase();
    row.style.display = txt.includes(kw) ? '' : 'none';
  });
}

function renderEmpSettingsTab(emp) {
  document.getElementById('emp-tab-settings').innerHTML = `
    <div class="emp-detail-body">
      <div class="settings-layout">
        <div class="settings-subnav">
          <div class="settings-subnav-item active">基本信息</div>
          <div class="settings-subnav-item">Prompt配置</div>
          <div class="settings-subnav-item">知识库</div>
        </div>
        <div class="settings-form">
          <div class="form-group"><div class="form-label">显示名称</div><input type="text" id="setName" value="${emp.name}"></div>
          <div class="form-group"><div class="form-label">描述</div><textarea id="setDesc">${emp.desc || ''}</textarea></div>
          <div class="form-row-2col">
            <div class="form-group"><div class="form-label">类型</div><select id="setType"><option ${emp.type === '通用' || !emp.type ? 'selected' : ''}>通用</option><option ${emp.type === '运维' ? 'selected' : ''}>运维</option><option ${emp.type === '开发' ? 'selected' : ''}>开发</option><option ${emp.type === '数据分析' ? 'selected' : ''}>数据分析</option></select></div>
            <div class="form-group"><div class="form-label">模型</div><select id="setModel"><option ${emp.model === 'deepseek-v4' || !emp.model ? 'selected' : ''}>deepseek-v4</option><option ${emp.model === 'deepseek-v3' ? 'selected' : ''}>deepseek-v3</option></select></div>
          </div>
          <div class="form-group"><div class="form-label">系统 Prompt</div><textarea id="setPrompt">${emp.prompt || ''}</textarea></div>
          <div class="form-actions"><button class="btn-primary-filled" onclick="saveEmpSettings('${emp.id}')">保存</button><button class="btn-outline" onclick="showEmpDetail('${emp.id}')">取消</button></div>
        </div>
      </div>
    </div>`;
}

async function saveEmpSettings(empId) {
  const body = {
    name: document.getElementById('setName').value.trim(),
    desc: document.getElementById('setDesc').value.trim(),
    type: document.getElementById('setType').value,
    model: document.getElementById('setModel').value,
    prompt: document.getElementById('setPrompt').value.trim(),
  };
  if (!body.name) { uiAlert({ title: '提示', message: '显示名称不能为空', type: 'warning' }); return; }
  try {
    await fetch('/api/employees/' + empId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    renderEmployees();
    showEmpDetail(empId);
  } catch (e) { uiAlert({ title: '保存失败', message: e.message, type: 'error' }); }
}

// 按业务分组聚合：空分组统一归「未分组」，未分组区块排最后
function groupByBizGroup(items, getGroup) {
  const map = new Map();
  (items || []).forEach(it => {
    const g = (getGroup(it) || '').trim() || '未分组';
    if (!map.has(g)) map.set(g, []);
    map.get(g).push(it);
  });
  const order = [...map.keys()].sort((a, b) => (a === '未分组' ? 1 : 0) - (b === '未分组' ? 1 : 0));
  return order.map(g => [g, map.get(g)]);
}

function fillGroupDatalist(listId, groups) {
  const dl = document.getElementById(listId);
  if (!dl) return;
  const uniq = [...new Set((groups || []).filter(Boolean))].sort();
  dl.innerHTML = uniq.map(g => `<option value="${escapeHtml(g)}"></option>`).join('');
}

async function loadSkillGroupOptions() {
  try {
    const r = await fetch('/api/skills').then(x => x.json());
    fillGroupDatalist('skillGroupOptions', (r.skills || []).map(s => (s.group || '').trim()));
  } catch (e) { /* datalist 为空仍可自由输入 */ }
}

async function loadServerGroupOptions() {
  try {
    const [sr, tr] = await Promise.all([
      fetch('/api/mcp-servers').then(x => x.json()),
      fetch('/api/mcp-tools').then(x => x.json())
    ]);
    const groups = [...(sr.servers || []), ...(tr.tools || [])].map(x => (x.group || '').trim());
    fillGroupDatalist('serverGroupOptions', groups);
    fillGroupDatalist('toolGroupOptions', groups);
  } catch (e) { /* 忽略 */ }
}

async function renderSkillsPage() {
  try {
    const r = await fetch('/api/skills').then(x => x.json());
    S.skills = r.skills || [];
    const tab = S.currentSkillTab;
    const list = S.skills.filter(s => s.category === tab);
    const kw = (S.skillKeyword || '').toLowerCase();
    const filtered = list.filter(s => !kw || (s.name || '').toLowerCase().includes(kw) || (s.desc || '').toLowerCase().includes(kw));
    const groups = groupByBizGroup(filtered, s => s.group);
    document.getElementById('skillCardGrid').innerHTML = groups.length
      ? groups.map(([g, items]) => `
          <div style="margin-bottom:22px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
              <span style="font-size:14px;font-weight:600;color:var(--c-text-h1);">${g}</span>
              <span class="tag" style="font-size:11px;">${items.length} 项</span>
            </div>
            <div class="skill-card-grid">${items.map(s => `
              <div class="skill-card" onclick="showSkillDetail('${s.id}')">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                  <div class="skill-name">${s.name}${s.id && s.id.startsWith('skill-c-') ? '<span class="tag" style="margin-left:6px;color:var(--c-primary);border-color:rgba(56,189,248,.4)">自定义</span>' : ''}</div>
                  <div style="display:flex;gap:6px;" onclick="event.stopPropagation()">
                    <button class="tb-btn" title="编辑" onclick="openEditSkill('${s.id}')" style="width:26px;height:26px;border-radius:6px;cursor:pointer;border:1px solid var(--c-border-light);background:transparent;color:var(--c-text-body);display:inline-flex;align-items:center;justify-content:center;">${icon('gear')}</button>
                    <button class="tb-btn" title="删除" onclick="deleteSkill('${s.id}')" style="width:26px;height:26px;border-radius:6px;cursor:pointer;border:1px solid var(--c-border-light);background:transparent;color:var(--c-danger);display:inline-flex;align-items:center;justify-content:center;">${icon('close')}</button>
                  </div>
                </div>
                <div class="skill-desc">${s.desc || ''}</div>
                <div class="skill-tags">${(s.tags || []).map(t => `<span class="tag">${t}</span>`).join('')}</div>
              </div>`).join('')}</div>
          </div>`).join('')
      : '<div class="todo-empty" style="padding:24px;border:1px dashed var(--c-border-light);border-radius:8px;text-align:center;color:var(--c-text-time);">暂无技能，点击右上角「+ 导入Skill」创建</div>';
    fillGroupDatalist('skillGroupOptions', S.skills.map(s => (s.group || '').trim()));
  } catch (e) { console.error(e); }
}

function searchSkills(val) { S.skillKeyword = val; renderSkillsPage(); }

function switchSkillTab(tab) {
  S.currentSkillTab = tab;
  document.querySelectorAll('#skillTabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  renderSkillsPage();
}

async function openCreateSkill() {
  SKILL_EDIT_ID = null;
  document.getElementById('skillModalTitle').textContent = '创建技能';
  document.getElementById('skillFormName').value = '';
  document.getElementById('skillFormDesc').value = '';
  document.getElementById('skillFormFlow').value = '';
  document.getElementById('skillFormGroup').value = '';
  document.getElementById('skillFormCategory').value = S.currentSkillTab && S.currentSkillTab !== 'all' ? S.currentSkillTab : 'custom';
  await loadSkillToolOptions([]);
  await loadSkillGroupOptions();
  document.getElementById('createSkillModal').classList.remove('hidden');
}

function closeCreateSkill() {
  document.getElementById('createSkillModal').classList.add('hidden');
  SKILL_EDIT_ID = null;
}

async function openEditSkill(id) {
  SKILL_EDIT_ID = id;
  document.getElementById('skillModalTitle').textContent = '编辑技能';
  try {
    const r = await fetch('/api/skills/' + id + '/detail').then(x => x.json());
    document.getElementById('skillFormName').value = r.name || '';
    document.getElementById('skillFormDesc').value = r.desc || '';
    document.getElementById('skillFormFlow').value = r.flow || r.prompt || '';
    document.getElementById('skillFormCategory').value = (['custom','market'].includes(r.category) ? r.category : 'custom');
    document.getElementById('skillFormGroup').value = r.group || '';
    const checked = (r.tools || []).map(t => t.id);
    await loadSkillToolOptions(checked);
    await loadSkillGroupOptions();
    document.getElementById('createSkillModal').classList.remove('hidden');
  } catch (e) { uiAlert({ title: '加载技能失败', message: e.message, type: 'error' }); }
}

async function loadSkillToolOptions(checkedIds) {
  try {
    const r = await fetch('/api/mcp-tools').then(x => x.json());
    const tools = r.tools || [];
    const checked = new Set(checkedIds || []);
    document.getElementById('skillFormTools').innerHTML = tools.length ? tools.map(t => `
      <label style="display:flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--c-border-light);border-radius:6px;cursor:pointer;background:var(--c-main-bg);">
        <input type="checkbox" value="${t.id}" ${checked.has(t.id) ? 'checked' : ''} style="accent-color:var(--c-primary);">
        <span style="font-size:13px;font-weight:500;">${t.name}</span>
        <span style="font-size:12px;color:var(--c-text-time);margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px;">${t.desc || ''}</span>
      </label>`).join('') : '<span style="color:var(--c-text-time);font-size:13px;padding:8px;">暂无可用工具，请先到「工具库」添加 MCP Server 并同步工具</span>';
  } catch (e) {
    document.getElementById('skillFormTools').innerHTML = '<span style="color:var(--c-danger);font-size:13px;">工具加载失败：' + e.message + '</span>';
  }
}

async function doCreateSkill() {
  const name = document.getElementById('skillFormName').value.trim();
  if (!name) { uiAlert({ title: '提示', message: '请输入技能名称', type: 'warning' }); return; }
  const payload = {
    name,
    desc: document.getElementById('skillFormDesc').value.trim(),
    flow: document.getElementById('skillFormFlow').value.trim(),
    category: document.getElementById('skillFormCategory').value,
    group: document.getElementById('skillFormGroup').value.trim(),
    tools: [...document.querySelectorAll('#skillFormTools input:checked')].map(i => i.value)
  };
  try {
    const url = SKILL_EDIT_ID ? '/api/skills/' + SKILL_EDIT_ID : '/api/skills';
    const method = SKILL_EDIT_ID ? 'PUT' : 'POST';
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '保存失败', message: (res.error || r.statusText), type: 'error' }); return; }
    uiAlert({ title: '保存成功', message: '技能「' + name + '」已保存', type: 'success' });
    closeCreateSkill();
    renderSkillsPage();
  } catch (e) { uiAlert({ title: '保存失败', message: e.message, type: 'error' }); }
}

async function deleteSkill(id) {
  if (!await uiConfirm({ title: '删除技能', message: '确认删除该技能？删除后数字员工将不再拥有该技能。', danger: true })) return;
  try {
    const r = await fetch('/api/skills/' + id, { method: 'DELETE' });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '删除失败', message: (res.error || r.statusText), type: 'error' }); return; }
    renderSkillsPage();
  } catch (e) { uiAlert({ title: '删除失败', message: e.message, type: 'error' }); }
}

async function showSkillDetail(id) {
  SKILL_DETAIL_ID = id;
  const r = await fetch('/api/skills/' + id + '/detail').then(x => x.json());
  document.getElementById('skillDetailTitle').textContent = r.name || 'Skill 详情';
  document.getElementById('skillDetailBody').innerHTML = `
    <p style="color:var(--c-text-secondary);margin-bottom:16px;line-height:1.6">${r.desc || ''}</p>
    <div class="detail-section">
      <div class="ds-title">基本信息</div>
      <div class="detail-info-grid">
        <span class="info-label">技能类型</span><span>${r.type || '-'}</span>
        <span class="info-label">分类</span><span>${r.category || '-'}</span>
        <span class="info-label">标签</span><span>${(r.tags || []).map(t => `<span class="tag">${t}</span>`).join('') || '-'}</span>
      </div>
    </div>
    <div class="detail-section">
      <div class="ds-title" style="display:flex;align-items:center;gap:6px;">${icon('gear')} 关联工具（${(r.tools || []).length}）</div>
      ${(r.tools || []).map(t => `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--c-border-light);border-radius:6px;margin-bottom:6px">
          <span style="display:inline-flex;color:var(--c-primary);">${icon('wrench')}</span>
          <span style="font-size:13px;font-weight:500">${t.name}</span>
          <span style="font-size:12px;color:var(--c-text-secondary);margin-left:auto;text-align:right">${t.desc || ''}</span>
        </div>`).join('') || '<span style="color:var(--c-text-secondary);font-size:13px">暂无关联工具</span>'}
    </div>
    <div class="detail-section">
      <div class="ds-title" style="display:flex;align-items:center;gap:6px;">${icon('clipboard')} 执行流程</div>
      <div style="font-size:13px;line-height:1.8;color:var(--c-text-body);white-space:pre-wrap;background:#0E1626;border:1px solid #1E2A44;border-radius:6px;padding:12px 16px">${r.flow || '暂无流程说明'}</div>
    </div>`;
  document.getElementById('skillDetailModal').classList.remove('hidden');
}

function closeSkillDetail() { document.getElementById('skillDetailModal').classList.add('hidden'); }

async function renderToolsPage() {
  try {
    const [sr, tr] = await Promise.all([
      fetch('/api/mcp-servers').then(x => x.json()),
      fetch('/api/mcp-tools').then(x => x.json())
    ]);
    S_TOOLS.servers = sr.servers || [];
    S_TOOLS.tools = tr.tools || [];
    renderToolTree();
    renderToolCards();
  } catch (e) { console.error(e); }
}

// ── 工具中心：左树右平铺（MCPHub 风格） ────────────────────────────
function encAttr(s) { return escapeHtml(String(s == null ? '' : s)).replace(/'/g, '&#39;'); }

function toolGroupOf(t) { return (t.group || '').trim() || '未分组'; }

// 构建 分组 → Server 两级树数据；仅当某分组下 Server 数 > 1 时才展示 Server 子层
function buildToolTreeData() {
  const groupNodes = groupByBizGroup(S_TOOLS.tools, t => t.group);
  return groupNodes.map(([g, tools]) => {
    const serverMap = new Map();
    tools.forEach(t => {
      const sid = t.server_id || '';
      if (!serverMap.has(sid)) serverMap.set(sid, { id: sid, name: t.server_name || '未关联Server', tools: [] });
      serverMap.get(sid).tools.push(t);
    });
    return { name: g, tools, servers: [...serverMap.values()] };
  });
}

function toolInScope(t) {
  const sel = TOOL_SEL;
  if (sel.type === 'all') return true;
  if (sel.type === 'group') return toolGroupOf(t) === sel.group;
  if (sel.type === 'server') return toolGroupOf(t) === sel.group && (t.server_id || '') === sel.serverId;
  return true;
}

function renderToolTree() {
  const panel = document.getElementById('toolTreePanel');
  if (!panel) return;
  const groupNodes = buildToolTreeData();
  const total = S_TOOLS.tools.length;
  const active = TOOL_SEL;
  const isRootActive = active.type === 'all';

  const rootHtml = `
    <div class="tree-head">工具分类</div>
    <div class="tree-node ${isRootActive ? 'active' : ''}" onclick="selectToolNode('all')">
      <span class="tree-caret placeholder"></span>
      <span class="tree-label">全部工具</span>
      <span class="tree-count">${total}</span>
    </div>`;

  const groupHtml = groupNodes.map(g => {
    const isActiveGroup = active.type !== 'all' && active.group === g.name;
    const multiServer = g.servers.length > 1;
    const expanded = multiServer && isActiveGroup && active.type === 'server';
    const serverRows = multiServer ? g.servers.map(s => {
      const isActiveServer = isActiveGroup && active.type === 'server' && active.serverId === s.id;
      const knownServer = !!s.id && S_TOOLS.servers.some(x => x.id === s.id);
      const ops = knownServer ? `
        <span class="tree-ops" onclick="event.stopPropagation()">
          <button class="tree-op" title="同步工具" onclick="syncServerTools('${encAttr(s.id)}')">${icon('refresh')}</button>
          <button class="tree-op" title="编辑" onclick="openServerModal('${encAttr(s.id)}')">${icon('gear')}</button>
          <button class="tree-op danger" title="删除" onclick="deleteServer('${encAttr(s.id)}')">${icon('close')}</button>
        </span>` : '';
      return `
        <div class="tree-node tree-node-server ${isActiveServer ? 'active' : ''}" onclick="selectToolNode('server','${encAttr(g.name)}','${encAttr(s.id)}','${encAttr(s.name)}')">
          <span class="tree-caret placeholder"></span>
          <span class="tree-dot"></span>
          <span class="tree-label">${escapeHtml(s.name)}</span>
          <span class="tree-count">${s.tools.length}</span>
          ${ops}
        </div>`;
    }).join('') : '';
    return `
      <div class="tree-branch">
        <div class="tree-node ${isActiveGroup ? 'active' : ''}" onclick="selectToolNode('group','${encAttr(g.name)}')">
          ${multiServer ? `<span class="tree-caret" onclick="event.stopPropagation();toggleTreeBranch(this)">${icon('chevronDown')}</span>` : `<span class="tree-caret placeholder"></span>`}
          <span class="tree-label">${escapeHtml(g.name)}</span>
          <span class="tree-count">${g.tools.length}</span>
        </div>
        ${multiServer ? `<div class="tree-children ${expanded ? '' : 'hidden'}">${serverRows}</div>` : ''}
      </div>`;
  }).join('');

  panel.innerHTML = rootHtml + groupHtml;
}

function toggleTreeBranch(caretEl) {
  const branch = caretEl.closest('.tree-branch');
  const children = branch ? branch.querySelector('.tree-children') : null;
  if (!children) return;
  children.classList.toggle('hidden');
  caretEl.classList.toggle('open');
}

function selectToolNode(type, group, serverId, serverName) {
  TOOL_SEL.type = type;
  TOOL_SEL.group = group || '';
  TOOL_SEL.serverId = serverId || '';
  TOOL_SEL.serverName = serverName || '';
  renderToolTree();
  renderToolCards();
}

function renderToolCards() {
  const kw = (document.getElementById('toolSearchInput')?.value || '').toLowerCase();
  const filtered = S_TOOLS.tools.filter(t => toolInScope(t) && (!kw ||
    (t.name || '').toLowerCase().includes(kw) ||
    (t.desc || '').toLowerCase().includes(kw) ||
    (t.server_name || '').toLowerCase().includes(kw) ||
    toolGroupOf(t).toLowerCase().includes(kw)));
  const grid = document.getElementById('toolCardGrid');
  if (!grid) return;
  const groups = groupByBizGroup(filtered, t => t.group);
  grid.innerHTML = groups.length
    ? groups.map(([g, items]) => `
        <div style="margin-bottom:22px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:14px;font-weight:600;color:var(--c-text-h1);">${escapeHtml(g)}</span>
            <span class="tag" style="font-size:11px;">${items.length} 项</span>
          </div>
          <div class="skill-card-grid">${items.map(t => toolCardHtml(t)).join('')}</div>
        </div>`).join('')
    : '<div class="todo-empty" style="padding:28px;border:1px dashed var(--c-border-light);border-radius:8px;text-align:center;color:var(--c-text-time);">暂无匹配的工具，试试调整左侧筛选或搜索关键词</div>';
}

function toolCardHtml(t) {
  return `
    <div class="skill-card" style="cursor:pointer;padding:14px 16px;" onclick="openToolDetail('${encAttr(t.id)}')">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="display:inline-flex;color:var(--c-primary);flex-shrink:0;">${icon('wrench')}</span>
        <span style="font-size:14px;font-weight:600;color:var(--c-text-h1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.name)}</span>
        <span class="tag" style="font-size:10px;flex-shrink:0;">${escapeHtml(t.method || 'POST')}</span>
      </div>
      <div style="font-size:12px;color:var(--c-text-time);margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">${escapeHtml(t.desc || '暂无描述')}</div>
      <div class="skill-tags" style="margin-top:auto;">
        <span class="tag" style="font-size:11px;color:var(--c-primary);border-color:rgba(56,189,248,.4);max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(t.server_name || '')}">${escapeHtml(t.server_name || '未关联Server')}</span>
        ${t.group ? `<span class="tag" style="font-size:11px;color:var(--c-warning,#f59e0b);border-color:rgba(245,158,11,.4);">${escapeHtml(t.group)}</span>` : ''}
        <span class="tag" style="font-size:11px;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.path || '/')}</span>
      </div>
    </div>`;
}

// ── 工具详情弹窗 ─────────────────────────────────────────────
function openToolDetail(toolId) {
  const t = (S_TOOLS.tools || []).find(x => x.id === toolId);
  if (!t) { uiAlert({ title: '提示', message: '未找到该工具', type: 'warning' }); return; }
  TOOL_DETAIL_ID = toolId;
  const server = S_TOOLS.servers.find(s => s.id === t.server_id);
  document.getElementById('toolDetailTitle').textContent = t.name || '工具详情';
  document.getElementById('toolDetailBody').innerHTML = toolDetailHtml(t, server);
  document.getElementById('toolDetailModal').classList.remove('hidden');
}

function closeToolDetail() {
  document.getElementById('toolDetailModal').classList.add('hidden');
  TOOL_DETAIL_ID = null;
}

function parseToolParams(schema) {
  if (!schema) return [];
  if (Array.isArray(schema)) return schema;
  if (schema.properties && typeof schema.properties === 'object') {
    const required = new Set(schema.required || []);
    return Object.entries(schema.properties).map(([name, v]) => ({
      name,
      type: v.type || 'string',
      required: required.has(name),
      desc: v.description || v.desc || ''
    }));
  }
  return [];
}

function toolDetailHtml(t, server) {
  const params = parseToolParams(t.params_schema);
  const paramRows = params.length
    ? params.map(p => `
      <tr>
        <td style="font-weight:600;color:var(--c-text-h1);">${escapeHtml(p.name || '')}</td>
        <td><span class="tag" style="font-size:11px;">${escapeHtml(p.type || 'string')}</span></td>
        <td>${p.required ? '<span style="color:var(--c-danger);font-size:12px;">必填</span>' : '<span style="color:var(--c-text-time);font-size:12px;">选填</span>'}</td>
        <td style="color:var(--c-text-body);font-size:12px;">${escapeHtml(p.desc || '-')}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--c-text-time);font-size:12px;padding:16px;">该工具无需参数</td></tr>';

  return `
    <div class="detail-block">
      <div class="detail-block-title">基本信息</div>
      <div class="detail-row"><span class="detail-label">工具名称</span><span class="detail-value">${escapeHtml(t.name || '-')}</span></div>
      <div class="detail-row"><span class="detail-label">工具 ID</span><span class="detail-value mono">${escapeHtml(t.id || '-')}</span></div>
      <div class="detail-row"><span class="detail-label">所属分组</span><span class="detail-value">${t.group ? `<span class="tag" style="color:var(--c-warning,#f59e0b);border-color:rgba(245,158,11,.4);">${escapeHtml(t.group)}</span>` : '<span class="tag">未分组</span>'}</span></div>
      <div class="detail-row"><span class="detail-label">请求方式</span><span class="detail-value"><span class="tag" style="color:var(--c-primary);border-color:rgba(56,189,248,.4);">${escapeHtml(t.method || 'POST')}</span> <code class="mono">${escapeHtml(t.path || '/')}</code></span></div>
      <div class="detail-row"><span class="detail-label">功能描述</span><span class="detail-value" style="white-space:pre-line;">${escapeHtml(t.desc || '暂无描述')}</span></div>
    </div>
    <div class="detail-block">
      <div class="detail-block-title">所属 MCP Server</div>
      ${server ? `
        <div class="detail-row"><span class="detail-label">名称</span><span class="detail-value">${escapeHtml(server.name || '')}</span></div>
        <div class="detail-row"><span class="detail-label">地址</span><span class="detail-value mono">${escapeHtml(server.base_url || '-')}</span></div>
        <div class="detail-row"><span class="detail-label">类型</span><span class="detail-value"><span class="tag" style="color:${server.type === 'remote' ? 'var(--c-primary)' : 'var(--c-success)'};border-color:${server.type === 'remote' ? 'rgba(56,189,248,.4)' : 'rgba(52,211,153,.4)'};">${server.type === 'remote' ? '远程' : '本地'}</span> <span class="tag">${server.status === 'online' ? '已连接' : '未同步'}</span></span></div>`
      : `<div class="detail-row"><span class="detail-label">名称</span><span class="detail-value">${escapeHtml(t.server_name || '未关联Server')}</span></div>`}
    </div>
    <div class="detail-block">
      <div class="detail-block-title">参数说明 <span class="tag" style="font-size:11px;">${params.length} 个</span></div>
      <table class="param-table">
        <thead><tr><th>参数名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
        <tbody>${paramRows}</tbody>
      </table>
    </div>`;
}

async function openServerModal(serverId) {
  SERVER_EDIT_ID = serverId || null;
  document.getElementById('serverModalTitle').textContent = serverId ? '编辑 MCP Server' : '添加 MCP Server';
  const f = { name: '', url: '', type: 'local', auth: 'none', desc: '', group: '' };
  if (serverId) {
    const s = S_TOOLS.servers.find(x => x.id === serverId) || {};
    f.name = s.name || ''; f.url = s.base_url || ''; f.type = s.type || 'local'; f.auth = s.auth || 'none'; f.desc = s.desc || ''; f.group = s.group || '';
  }
  document.getElementById('serverFormName').value = f.name;
  document.getElementById('serverFormUrl').value = f.url;
  document.getElementById('serverFormType').value = f.type;
  document.getElementById('serverFormAuth').value = f.auth;
  document.getElementById('serverFormDesc').value = f.desc;
  document.getElementById('serverFormGroup').value = f.group;
  await loadServerGroupOptions();
  document.getElementById('serverModal').classList.remove('hidden');
}

function closeServerModal() { document.getElementById('serverModal').classList.add('hidden'); SERVER_EDIT_ID = null; }

async function doSaveServer() {
  const name = document.getElementById('serverFormName').value.trim();
  const url = document.getElementById('serverFormUrl').value.trim();
  if (!name) { uiAlert({ title: '提示', message: '请输入 Server 名称', type: 'warning' }); return; }
  if (!url) { uiAlert({ title: '提示', message: '请输入 Base URL', type: 'warning' }); return; }
  const payload = {
    name,
    base_url: url,
    type: document.getElementById('serverFormType').value,
    auth: document.getElementById('serverFormAuth').value,
    group: document.getElementById('serverFormGroup').value.trim(),
    desc: document.getElementById('serverFormDesc').value.trim()
  };
  try {
    const url2 = SERVER_EDIT_ID ? '/api/mcp-servers/' + SERVER_EDIT_ID : '/api/mcp-servers';
    const method = SERVER_EDIT_ID ? 'PUT' : 'POST';
    const r = await fetch(url2, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '保存失败', message: (res.error || r.statusText), type: 'error' }); return; }
    closeServerModal();
    renderToolsPage();
  } catch (e) { uiAlert({ title: '保存失败', message: e.message, type: 'error' }); }
}

async function syncServerTools(serverId) {
  if (!await uiConfirm({ title: '同步工具', message: '将从该 Server 的 /tools 端点拉取并同步工具清单，是否继续？' })) return;
  try {
    const r = await fetch('/api/mcp-servers/' + serverId + '/sync', { method: 'POST' });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '同步失败', message: (res.error || r.statusText), type: 'error' }); return; }
    uiAlert({ title: '同步完成', message: '同步完成，共发现 ' + (res.count || 0) + ' 个工具', type: 'success' });
    renderToolsPage();
  } catch (e) { uiAlert({ title: '同步失败', message: e.message, type: 'error' }); }
}

function editToolGroup(toolId) {
  const t = (S_TOOLS.tools || []).find(x => x.id === toolId);
  if (!t) { uiAlert({ title: '提示', message: '未找到该工具', type: 'warning' }); return; }
  TOOL_GROUP_EDIT_ID = toolId;
  document.getElementById('toolGroupToolName').textContent = (t.name || toolId) + (t.server_name ? ' · ' + t.server_name : '');
  document.getElementById('toolGroupInput').value = t.group || '';
  loadServerGroupOptions();
  document.getElementById('toolGroupModal').classList.remove('hidden');
}

function closeToolGroupModal() {
  document.getElementById('toolGroupModal').classList.add('hidden');
  TOOL_GROUP_EDIT_ID = null;
}

async function doSaveToolGroup() {
  if (!TOOL_GROUP_EDIT_ID) return;
  const group = document.getElementById('toolGroupInput').value.trim();
  try {
    const r = await fetch('/api/mcp-tools/' + TOOL_GROUP_EDIT_ID, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group })
    });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '保存失败', message: (res.error || r.statusText), type: 'error' }); return; }
    uiAlert({ title: '保存成功', message: '工具分组已更新', type: 'success' });
    closeToolGroupModal();
    renderToolsPage();
  } catch (e) { uiAlert({ title: '保存失败', message: e.message, type: 'error' }); }
}

async function deleteServer(serverId) {
  if (!await uiConfirm({ title: '删除 Server', message: '确认删除该 MCP Server？其下所有工具及技能绑定将一并删除。', danger: true })) return;
  try {
    const r = await fetch('/api/mcp-servers/' + serverId, { method: 'DELETE' });
    const res = await r.json();
    if (!r.ok || !res.success) { uiAlert({ title: '删除失败', message: (res.error || r.statusText), type: 'error' }); return; }
    renderToolsPage();
  } catch (e) { uiAlert({ title: '删除失败', message: e.message, type: 'error' }); }
}

async function kbApi(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function kbLoad() {
  try {
    const [b, e] = await Promise.all([kbApi('/api/knowledge/bases'), kbApi('/api/employees')]);
    kbKBS = b.knowledge_bases || [];
    kbEMPS = e.employees || [];
    kbRenderList();
  } catch (err) { showToast(err.message, true); }
}

function kbRenderList() {
  kb$('kbKpiTotal').textContent = kbKBS.length;
  kb$('kbKpiDocs').textContent = kbKBS.reduce((s, k) => s + (k.doc_count || 0), 0);
  kb$('kbKpiChunks').textContent = kbKBS.reduce((s, k) => s + (k.chunk_count || 0), 0);
  kb$('kbKpiEmps').textContent = new Set(kbKBS.flatMap(k => (k.employees || []).map(e => e.id))).size;
  const grid = kb$('kbGrid');
  if (!kbKBS.length) {
    grid.innerHTML = '<div class="kb-empty" style="grid-column:1/-1;">还没有知识库。<br>点击右上角「新建知识库」，然后上传你的文档。</div>';
    return;
  }
  grid.innerHTML = kbKBS.map(k => `
    <div class="kb-card">
      <div class="kb-name">📖 ${escapeHtml(k.name)}</div>
      <div class="kb-desc">${escapeHtml(k.description || '暂无描述')}</div>
      <div class="kb-stats">
        <span class="kb-stat">文档<b>${k.doc_count || 0}</b></span>
        <span class="kb-stat">切块<b>${k.chunk_count || 0}</b></span>
      </div>
      <div class="kb-emps">${(k.employees || []).map(e => `<span class="kb-badge">${escapeHtml(e.name)}</span>`).join('') || '<span class="kb-badge empty">未绑定智能体</span>'}</div>
      <div class="kb-actions">
        <button class="btn-primary" style="height:32px;padding:0 14px;font-size:12px;" onclick="kbOpenDetail('${k.id}')">管理</button>
        <button class="card-btn" onclick="kbOpenBind('${k.id}')">绑定</button>
        <button class="card-btn danger" onclick="kbDeleteBase('${k.id}')">删除</button>
      </div>
    </div>`).join('');
}

function kbOpenDetail(id) {
  kbCUR = kbKBS.find(k => k.id === id);
  if (!kbCUR) return;
  kbCUR_PAGE = 0;
  kb$('kbDName').textContent = '📖 ' + kbCUR.name;
  kb$('kbDStats').textContent = `文档 ${kbCUR.doc_count || 0} · 切块 ${kbCUR.chunk_count || 0}`;
  kb$('kbDStats').className = 'kb-badge';
  kb$('kbDDesc').textContent = kbCUR.description || '暂无描述';
  kb$('kbDEmps').innerHTML = (kbCUR.employees || []).map(e => `<span class="kb-badge">${escapeHtml(e.name)}</span>`).join('') || '<span class="kb-badge empty">未绑定智能体</span>';
  kb$('kbListView').classList.add('hidden');
  kb$('kbDetailView').classList.remove('hidden');
  kbLoadChunks();
}

function kbShowList() {
  kb$('kbDetailView').classList.add('hidden');
  kb$('kbListView').classList.remove('hidden');
  kbCUR = null;
  kbRenderList();
}

async function kbLoadChunks() {
  if (!kbCUR) return;
  const w = kb$('kbChunkList');
  w.innerHTML = '<div class="kb-empty">加载中...</div>';
  try {
    const j = await kbApi(`/api/knowledge/${kbCUR.id}/chunks?offset=${kbCUR_PAGE * kbPAGE_SIZE}&limit=${kbPAGE_SIZE}`);
    const chunks = j.chunks || [];
    const totalPages = Math.max(1, Math.ceil((j.total || chunks.length) / kbPAGE_SIZE));
    if (!chunks.length) { w.innerHTML = '<div class="kb-empty">暂无切块，上传文档后将自动切块。</div>'; kb$('kbPager').innerHTML = ''; return; }
    w.innerHTML = chunks.map(c => `<div class="kb-chunk-item">
      <div class="kb-meta"><span>#${c.chunk_index || ''}</span><span style="color:var(--c-text-placeholder);">${escapeHtml(c.source || '')}</span><span style="margin-left:auto;">${c.chars || 0} 字符</span><button class="card-btn danger" style="height:24px;padding:0 8px;font-size:11px;" onclick="kbDeleteChunk('${c.id}')">删除</button></div>
      <pre>${escapeHtml(c.content || '')}</pre></div>`).join('');
    kb$('kbPager').innerHTML = `<button class="card-btn" ${kbCUR_PAGE === 0 ? 'disabled' : ''} onclick="kbGoPage(${kbCUR_PAGE - 1})">上一页</button><span>第 ${kbCUR_PAGE + 1} / ${totalPages} 页</span><button class="card-btn" ${kbCUR_PAGE + 1 >= totalPages ? 'disabled' : ''} onclick="kbGoPage(${kbCUR_PAGE + 1})">下一页</button>`;
  } catch (err) { w.innerHTML = `<div class="kb-empty">加载失败：${escapeHtml(err.message)}</div>`; }
}

function kbGoPage(p) { kbCUR_PAGE = p; kbLoadChunks(); }

async function kbDeleteChunk(chunkId) {
  if (!await uiConfirm({ title: '删除切块', message: '确定删除该切块？', danger: true })) return;
  try {
    await kbApi(`/api/knowledge/chunks/${chunkId}`, { method: 'DELETE' });
    showToast('切块已删除');
    kbLoadChunks();
  } catch (err) { showToast(err.message, true); }
}

async function kbRebuildIndex() {
  if (!kbCUR) return;
  if (!await uiConfirm({ title: '重建索引', message: `确定重建「${kbCUR.name}」的索引？` })) return;
  try {
    const j = await kbApi(`/api/knowledge/${kbCUR.id}/rebuild`, { method: 'POST' });
    showToast(`重建完成：文档 ${j.result ? j.result.doc_count : '?'} / 切块 ${j.result ? j.result.chunk_count : '?'}`);
    kbLoad();
    kbOpenDetail(kbCUR.id);
  } catch (err) { showToast(err.message, true); }
}

async function kbDeleteBase(id) {
  const kb = (id ? kbKBS.find(k => k.id === id) : kbCUR) || {};
  if (!await uiConfirm({ title: '删除知识库', message: `确定删除知识库「${kb.name || ''}」？其下所有文档与切块将一并删除。`, danger: true })) return;
  try {
    await kbApi(`/api/knowledge/bases/${kb.id}`, { method: 'DELETE' });
    showToast('知识库已删除');
    if (id) kbLoad();
    else { kbShowList(); kbLoad(); }
  } catch (err) { showToast(err.message, true); }
}

function kbOpenUpload() {
  kb$('kbUpKbName').textContent = kbCUR.name;
  kb$('kbUploadList').innerHTML = '';
  kb$('kbFileInput').value = '';
  kb$('kbFileDrop').classList.remove('drag');
  kb$('kbUploadOverlay').classList.remove('hidden');
}

function kbCloseUpload() { kb$('kbUploadOverlay').classList.add('hidden'); }

function kbSetupDrop() {
  const drop = kb$('kbFileDrop');
  const input = kb$('kbFileInput');
  if (!drop) return;
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
  drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('drag'); kbHandleFiles(e.dataTransfer.files); });
  input.addEventListener('change', () => kbHandleFiles(input.files));
}

function kbHandleFiles(files) {
  if (!kbCUR || !files || !files.length) return;
  const list = kb$('kbUploadList');
  Array.from(files).forEach(f => {
    const el = document.createElement('div');
    el.className = 'kb-upload-item';
    el.innerHTML = `<span style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(f.name)}</span><div class="kb-bar"><i></i></div><span class="kb-st">0%</span>`;
    list.appendChild(el);
    const fd = new FormData();
    fd.append('file', f);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/knowledge/${kbCUR.id}/upload`);
    xhr.upload.onprogress = ev => {
      if (ev.lengthComputable) {
        const pct = Math.round(ev.loaded / ev.total * 100);
        el.querySelector('.kb-bar i').style.width = pct + '%';
        el.querySelector('.kb-st').textContent = pct + '%';
      }
    };
    const finish = () => {
      if (list.querySelectorAll('.kb-upload-item:not(.ok):not(.fail)').length === 0) {
        setTimeout(() => { kbLoadChunks(); kbLoad(); }, 300);
      }
    };
    xhr.onload = () => {
      let msg = '';
      try { msg = JSON.parse(xhr.responseText).error || ''; } catch (e) {}
      if (xhr.status === 200) { el.classList.add('ok'); el.querySelector('.kb-st').textContent = '✓ 已上传'; }
      else { el.classList.add('fail'); el.querySelector('.kb-st').textContent = '✗ ' + (msg || xhr.status); }
      finish();
    };
    xhr.onerror = () => { el.classList.add('fail'); el.querySelector('.kb-st').textContent = '✗ 网络错误'; finish(); };
    xhr.send(fd);
  });
}

function kbOpenBind(id) {
  kbBIND_KB_ID = id || (kbCUR && kbCUR.id);
  const kb = kbKBS.find(k => k.id === kbBIND_KB_ID);
  if (!kb) return;
  kb$('kbBindKbName').textContent = kb.name;
  const cur = new Set((kb.employees || []).map(e => e.id));
  kb$('kbBindEmpList').innerHTML = kbEMPS.length ? kbEMPS.map(e => `
    <label class="kb-bind-item"><input type="checkbox" value="${e.id}" ${cur.has(e.id) ? 'checked' : ''}><span class="kb-bind-name">${escapeHtml(e.name)}</span><span class="kb-bind-tag">${escapeHtml(e.role || '')}</span></label>`).join('') : '<div class="kb-empty">暂无智能体</div>';
  kb$('kbBindOverlay').classList.remove('hidden');
}

function kbCloseBind() { kb$('kbBindOverlay').classList.add('hidden'); }

async function kbSubmitBind() {
  const ids = Array.from(kb$('kbBindEmpList').querySelectorAll('input:checked')).map(i => i.value);
  try {
    await kbApi(`/api/knowledge/${kbBIND_KB_ID}/bind`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employee_ids: ids }) });
    showToast('绑定已保存');
    kbCloseBind();
    await kbLoad();
    if (kbCUR) { const nk = kbKBS.find(k => k.id === kbCUR.id); if (nk) kbCUR = nk; }
  } catch (err) { showToast(err.message, true); }
}

function kbOpenCreate() { kb$('kbCreateOverlay').classList.remove('hidden'); kb$('kbNewName').value = ''; kb$('kbNewDesc').value = ''; }

function kbCloseCreate() { kb$('kbCreateOverlay').classList.add('hidden'); }

async function kbSubmitCreate() {
  const name = kb$('kbNewName').value.trim();
  if (!name) { showToast('请输入知识库名称', true); return; }
  try {
    await kbApi('/api/knowledge/bases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description: kb$('kbNewDesc').value.trim() }) });
    showToast('知识库已创建');
    kbCloseCreate();
    kbLoad();
  } catch (err) { showToast(err.message, true); }
}

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

// 工作成果：9006 业务平台外链卡片墙
function renderWork() {
  const grid = document.getElementById('workCardGrid');
  if (!grid) return;
  const links = [
    { title: '业务数据平台', desc: '经营指标 / 报表中心 / 数据分析', icon: 'chart', url: BIZ_9006_BASE + '/' },
    { title: '运维工单中心', desc: '工单流转 / 处置跟踪 / 服务台', icon: 'ticket', url: BIZ_9006_BASE + '/tickets' },
    { title: '资产配置库', desc: 'CMDB 资产 / 配置项 / 变更记录', icon: 'server', url: BIZ_9006_BASE + '/cmdb' },
    { title: '告警管理台', desc: '统一告警 / 通知策略 / 值班安排', icon: 'bell', url: BIZ_9006_BASE + '/alerts' },
  ];
  grid.innerHTML = links.map(l => `
    <a class="work-card" href="${l.url}" target="_blank" rel="noopener">
      <div class="work-card-icon">${icon(l.icon)}</div>
      <div class="work-card-title">${escapeHtml(l.title)}</div>
      <div class="work-card-desc">${escapeHtml(l.desc)}</div>
      <div class="work-card-open">打开平台 <span>↗</span></div>
    </a>`).join('');
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
