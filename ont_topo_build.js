/* 本体拓扑与一致性：纯字符串渲染器（无 DOM 依赖，可在 node 与浏览器共用）。
   输入 spec = {CONCEPTS,RELATIONS,ACTIONS,INVARIANTS,RULES,ACTION_REGISTRY}
   输出 SVG 字符串 / HTML 字符串。 */
(function (global) {
  'use strict';

  // ── 工具：递归收集 eq 规则里的 {field,val} ───────────────────────────
  function collectEq(node, out) {
    if (!node || typeof node !== 'object') return out;
    if (Array.isArray(node)) { node.forEach(function (n) { collectEq(n, out); }); return out; }
    var keys = Object.keys(node);
    if (keys.length === 1) {
      var op = keys[0], arg = node[op];
      if (op === 'eq' && Array.isArray(arg) && arg.length === 2) {
        out.push({ field: arg[0], val: arg[1] });
      } else if (op === 'and' || op === 'or' || op === 'not') {
        collectEq(arg, out);
      }
    }
    return out;
  }

  // 关系签名里的小写 token → 概念 id（仅当映射后是合法概念，丢弃噪声 token）
  var ALIAS = {
    task: 'InquiryTask', supplier: 'Supplier', person: 'Person', quote: 'Quote',
    approval: 'Approval', order: 'Order', shipment: 'Shipment', tracking: 'Shipment',
    approver: 'Approver'
  };
  function resolve(token, validSet) {
    if (!token) return null;
    token = token.trim().replace(/[{}]/g, '');
    if (ALIAS[token]) token = ALIAS[token];
    if (validSet && validSet.indexOf(token) < 0) return null; // 非概念噪声丢弃
    return token;
  }
  function resolveRange(rangeStr, validSet) {
    var toks = String(rangeStr || '').split(/[,\s{}]+/).filter(Boolean);
    var out = [];
    toks.forEach(function (t) { var r = resolve(t, validSet); if (r) out.push(r); });
    return Array.from(new Set(out));
  }

  // ── 概念 × 关系图 ─────────────────────────────────────────────────
  function conceptGraph(spec) {
    var concepts = spec.CONCEPTS || {};
    var relations = spec.RELATIONS || {};
    var validSet = Object.keys(concepts);
    var nodes = validSet.map(function (id) {
      return { id: id, label: id, desc: concepts[id], group: 'concept' };
    });
    var edges = [], unary = [], seenEdge = {};
    Object.keys(relations).forEach(function (sig) {
      var desc = relations[sig];
      var m = sig.match(/^([^(]+)\.([^()]+)\(([^)]*)\)$/);
      if (!m) {
        var um = sig.match(/^([^.]+)\.([^.]+)$/);
        if (um) { var un = resolve(um[1], validSet); if (un) unary.push({ node: un, prop: um[2], desc: desc }); }
        return;
      }
      var dom = resolve(m[1], validSet);
      var rel = m[2];
      var rngs = resolveRange(m[3], validSet);
      rngs.forEach(function (r) {
        if (!dom || !r) return;
        var key = dom + '|' + rel + '|' + r;
        if (seenEdge[key]) return;
        seenEdge[key] = 1;
        edges.push({ from: dom, to: r, label: rel });
      });
    });
    var touched = {};
    edges.forEach(function (e) { touched[e.from] = 1; touched[e.to] = 1; });
    unary.forEach(function (u) { touched[u.node] = 1; });
    var isolated = nodes.filter(function (n) { return !touched[n.id]; }).map(function (n) { return n.id; });
    return { nodes: nodes, edges: edges, unary: unary, isolated: isolated };
  }

  // ── 动作 – 状态映射图 ─────────────────────────────────────────────
  var STATUS_ORDER = ['R_FR02_MISSING_FIELDS', 'R_INIT', 'R_SEND', 'INVITE_QUOTE',
    'QUOTE_COLLECT_DONE', 'R_APPROVAL', 'R_ORDER', 'R_WAIT_ENGINEER_CLOSE',
    'R_CLOSED', 'R_SETTLE', 'CLOSED_ABORT', 'CLOSED_MANUAL'];
  function actionMap(spec) {
    var actions = spec.ACTIONS || {};
    var reg = spec.ACTION_REGISTRY || {};
    var rules = spec.RULES || [];
    var precond = {}, succ = {}, statuses = {};
    rules.forEach(function (r) {
      var eqs = collectEq(r.check, []);
      eqs.forEach(function (e) {
        if ((e.field === 'internal_status' || e.field === 'external_status') && typeof e.val === 'string') {
          precond[r.target] = precond[r.target] || {};
          precond[r.target][e.val] = 1; statuses[e.val] = 1;
        }
      });
    });
    Object.keys(reg).forEach(function (name) {
      var r = reg[name];
      [r.next_internal, r.next_external].forEach(function (s) {
        if (s) { succ[name] = succ[name] || {}; succ[name][s] = 1; statuses[s] = 1; }
      });
    });
    var statusList = Object.keys(statuses).sort(function (a, b) {
      var ia = STATUS_ORDER.indexOf(a), ib = STATUS_ORDER.indexOf(b);
      if (ia < 0) ia = 999; if (ib < 0) ib = 999; return ia - ib;
    });
    var actionList = Object.keys(actions);
    return { statuses: statusList, actions: actionList, precond: precond, succ: succ };
  }

  // ── 声明 ↔ 执行 一致性校验 ────────────────────────────────────────
  function health(spec) {
    var actions = Object.keys(spec.ACTIONS || {});
    var reg = Object.keys(spec.ACTION_REGISTRY || {});
    var rulesTargets = (spec.RULES || []).map(function (r) { return r.target; });
    var issues = [];
    actions.filter(function (a) { return reg.indexOf(a) < 0; }).forEach(function (a) {
      issues.push({ sev: 'warn', msg: '动作声明存在但未注册到 ACTION_REGISTRY：' + a + '（孤儿声明，运行时不执行）' });
    });
    reg.filter(function (a) { return actions.indexOf(a) < 0; }).forEach(function (a) {
      issues.push({ sev: 'error', msg: '注册表存在但本体未声明：' + a });
    });
    rulesTargets.filter(function (t) { return actions.indexOf(t) < 0; }).forEach(function (t) {
      issues.push({ sev: 'error', msg: '规则目标未声明动作：' + t });
    });
    // 状态词表漂移：规则前置引用的状态 vs 注册表后继状态
    var ruleStatuses = {}, regStatuses = {};
    (spec.RULES || []).forEach(function (r) {
      collectEq(r.check, []).forEach(function (e) {
        if ((e.field === 'internal_status' || e.field === 'external_status') && typeof e.val === 'string') ruleStatuses[e.val] = 1;
      });
    });
    Object.keys(spec.ACTION_REGISTRY || {}).forEach(function (name) {
      var rr = (spec.ACTION_REGISTRY || {})[name];
      [rr.next_internal, rr.next_external].forEach(function (s) { if (s) regStatuses[s] = 1; });
    });
    Object.keys(ruleStatuses).forEach(function (s) {
      if (!regStatuses[s]) issues.push({ sev: 'warn', msg: '状态命名漂移：规则前置引用「' + s + '」，但注册表后继状态中无此值（如 R_ORDER vs ORDER_CONFIRM、R_WAIT_ENGINEER_CLOSE vs WAIT_ENGINEER_CLOSE）——动作→状态链条在图上会断开' });
    });
    Object.keys(regStatuses).forEach(function (s) {
      if (!ruleStatuses[s]) issues.push({ sev: 'info', msg: '注册表后继状态「' + s + '」未被任何规则前置引用（单向出口，仅作展示）' });
    });
    var enforced = ['createTask'];
    var uniqTargets = Array.from(new Set(rulesTargets));
    var unenforced = uniqTargets.filter(function (t) { return enforced.indexOf(t) < 0; });
    if (unenforced.length) {
      issues.push({ sev: 'warn', msg: '声明式规则仅 ' + enforced.join('/') + ' 在运行时被校验器实际调用；其余 ' +
        unenforced.length + ' 条规则（' + unenforced.join('、') + '）当前不被决策器执行，流程由 decision.py 硬编码状态机驱动——属架构债/声明↔执行漂移' });
    }
    return issues;
  }

  // ── SVG：圆形布局（概念图）───────────────────────────────────────
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function radialSvg(g, opts) {
    opts = opts || {};
    var W = 720, H = 480, cx = W / 2, cy = H / 2, R = 175;
    var ns = g.nodes, n = ns.length;
    var pos = {};
    ns.forEach(function (nd, i) {
      var ang = (Math.PI * 2 * i) / Math.max(n, 1) - Math.PI / 2;
      pos[nd.id] = { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
    });
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="ont-svg" width="100%">';
    // edges
    g.edges.forEach(function (e) {
      var a = pos[e.from], b = pos[e.to]; if (!a || !b) return;
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      svg += '<g class="ont-edge" data-from="' + esc(e.from) + '" data-to="' + esc(e.to) + '">' +
        '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" />' +
        '<text x="' + mx + '" y="' + my + '" class="ont-edge-label">' + esc(e.label) + '</text></g>';
    });
    // unary props as badges near node
    // nodes
    ns.forEach(function (nd) {
      var p = pos[nd.id];
      var iso = g.isolated.indexOf(nd.id) >= 0;
      svg += '<g class="ont-node ont-node-concept' + (iso ? ' ont-iso' : '') + '" data-id="' + esc(nd.id) + '" tabindex="0">' +
        '<circle cx="' + p.x + '" cy="' + p.y + '" r="26" />' +
        '<text x="' + p.x + '" y="' + p.y + 4 + '" class="ont-node-label">' + esc(nd.label) + '</text></g>';
    });
    svg += '</svg>';
    return svg;
  }

  // ── SVG：双列（动作映射图）──────────────────────────────────────
  function bipartiteSvg(am) {
    var W = 760, rowH = 34, padT = 30, padB = 20;
    var H = Math.max(am.statuses.length, am.actions.length) * rowH + padT + padB;
    var colL = 170, colR = W - 170;
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="ont-svg" width="100%">';
    var sY = {}, aY = {};
    am.statuses.forEach(function (s, i) { sY[s] = padT + i * rowH + rowH / 2; });
    am.actions.forEach(function (a, i) { aY[a] = padT + i * rowH + rowH / 2; });
    // edges precond: status -> action
    am.actions.forEach(function (a) {
      var prec = am.precond[a] || {};
      Object.keys(prec).forEach(function (s) {
        if (!sY[s] || !aY[a]) return;
        svg += '<g class="ont-edge ont-pre"><line x1="' + colL + '" y1="' + sY[s] + '" x2="' + colR + '" y2="' + aY[a] + '" />' +
          '<text x="' + ((colL + colR) / 2) + '" y="' + ((sY[s] + aY[a]) / 2 - 4) + '" class="ont-edge-sub">前置</text></g>';
      });
      var sc = am.succ[a] || {};
      Object.keys(sc).forEach(function (s) {
        if (!sY[s] || !aY[a]) return;
        svg += '<g class="ont-edge ont-succ"><line x1="' + colR + '" y1="' + aY[a] + '" x2="' + colL + '" y2="' + sY[s] + '" />' +
          '<text x="' + ((colL + colR) / 2) + '" y="' + ((aY[a] + sY[s]) / 2 - 4) + '" class="ont-edge-sub">后继</text></g>';
      });
    });
    am.statuses.forEach(function (s) {
      svg += '<g class="ont-node ont-node-status" data-status="' + esc(s) + '"><rect x="' + (colL - 150) + '" y="' + (sY[s] - 12) + '" width="150" height="24" rx="6"/><text x="' + colL + '" y="' + (sY[s] + 4) + '" class="ont-node-label" text-anchor="middle">' + esc(s) + '</text></g>';
    });
    am.actions.forEach(function (a) {
      svg += '<g class="ont-node ont-node-action" data-action="' + esc(a) + '" tabindex="0"><rect x="' + (colR - 90) + '" y="' + (aY[a] - 12) + '" width="180" height="24" rx="12"/><text x="' + colR + '" y="' + (aY[a] + 4) + '" class="ont-node-label" text-anchor="middle">' + esc(a) + '</text></g>';
    });
    svg += '</svg>';
    return svg;
  }

  function buildAll(spec) {
    var cg = conceptGraph(spec);
    var am = actionMap(spec);
    var h = health(spec);
    return {
      conceptSvg: radialSvg(cg, {}),
      conceptIsolated: cg.isolated,
      actionSvg: bipartiteSvg(am),
      health: h,
      conceptCount: cg.nodes.length,
      edgeCount: cg.edges.length,
      statusCount: am.statuses.length,
      actionCount: am.actions.length
    };
  }

  global.OntTopo = {
    conceptGraph: conceptGraph, actionMap: actionMap, health: health,
    radialSvg: radialSvg, bipartiteSvg: bipartiteSvg, buildAll: buildAll,
    collectEq: collectEq, STATUS_ORDER: STATUS_ORDER
  };
})(typeof window !== 'undefined' ? window : globalThis);
