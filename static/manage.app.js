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
    const groups = groupByBizGroup(skills, s => s.group);
    document.getElementById('empSkillPool').innerHTML = groups.length ? groups.map(([g, items]) => `
      <div style="width:100%;margin-bottom:18px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
          <span style="font-size:14px;font-weight:600;color:var(--c-text-h1);">${g}</span>
          <span class="tag" style="font-size:11px;">${items.length} 项</span>
        </div>
        <div class="skill-mgr-cards">${items.map(s => {
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
              <span>分类：${s.category || '-'}${s.group ? ' · 分组：' + s.group : ''}</span>
              <span style="font-size:12px;color:${active ? 'var(--c-primary)' : 'var(--c-text-time)'};">${active ? '使用中' : '未使用'}</span>
            </div>
          </div>`;
        }).join('')}</div>
      </div>`).join('') : '<div class="todo-empty" style="grid-column:1/-1;border:1px dashed var(--c-border-light);border-radius:8px;text-align:center;color:var(--c-text-time);padding:24px;">后台能力池暂无技能，请到「后台管理 → 技能中心」配置</div>';
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
  const groups = groupByBizGroup(tools, t => t.group);
  document.getElementById('empMcpPool').innerHTML = groups.length ? groups.map(([g, items]) => `
      <div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <span style="font-size:14px;font-weight:600;color:var(--c-text-h1);">${g}</span>
          <span class="tag" style="font-size:11px;">${items.length} 项</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;">${items.map(t => `
          <div class="tool-card-detail mcp-tool-row" style="display:flex;align-items:center;gap:10px;">
            <div class="tool-info">
              <span class="tool-id">${t.name}</span>
              <span class="tool-desc-cn">${t.desc || ''}</span>
            </div>
            <span class="tool-tag" style="margin-left:auto;color:var(--c-text-time);">来自技能</span>
          </div>`).join('')}</div>
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

async function showSkillDetail(id) {
  try {
    const r = await fetch('/api/skills/' + id + '/detail').then(x => x.json());
    if (r && r.error) throw new Error(r.error);
    document.getElementById('skillDetailTitle').textContent = r.name || '技能详情';
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
  } catch (e) {
    showToast('技能详情加载失败：' + (e.message || e), true);
  }
}

function closeSkillDetail() { document.getElementById('skillDetailModal').classList.add('hidden'); }

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
