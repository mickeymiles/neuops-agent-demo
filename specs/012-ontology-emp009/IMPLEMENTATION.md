# 本体轨 emp-009 备件采购 — 实现现状与后续优化基础 (V1.0)

> Document Version: V1.0（实现落地基线，供后续优化参考）
> Date: 2026-08-31
> Component: emp-009 + 本体轨（本体表 + 知识规则层 + 动作注册表 + 规则校验引擎 + LLM 决策层）
> 配套文档：行为契约 `spec.md`（V0.1 规划）、设计 `design.md`（V0.2 目标范式）。**本文档记录的是"实际已落地、已验证"的状态，spec/design 中的 TODO 多数已在本体轨代码内完成。**
> 仓库：`/Users/macbook/AI-Agent/neuops-agent-demo`（端口 9007，服务器部署在 `122.51.98.98:/home/ubuntu/neuops-agent-demo`）

---

## 0. 一句话结论

本体轨 emp-009 的备件采购全链路 **A（发起询价）→ B（分发询价）→ 报价 → D（审批汇总）→ E（订货确认）→ F（快递单号）→ G（结算）** 已经**真实邮箱 + 服务器 009 主脑**端到端跑通，单元测试 57 例全绿。**注：G（结算）当前默认关闭**——受 `ONT_SETTLEMENT_ENABLED`（默认 `0`）控制，仅 A→F 实际生效；置 `1` 即恢复工程师"更换完成"触发 + 向供应商发结算邮件 G。本文档固化"现在有什么、验证到什么程度、哪些还能优化"，作为后续迭代基线。

---

## 1. 总体架构与边界（实际）

| 维度 | 现状 |
|---|---|
| 决策主体 | **LLM 决策回路**（`llm.py` + `decision.py`）+ 规则校验引擎（`knowledge.py`/`ontology.py`），`via_llm` 已修复生效；规则兜底 |
| 业务规则位置 | **声明式知识层** `app/ontology/knowledge.py`（`KNO-R-01` 规则集 + 极小表达式求值器），非全硬编码 |
| 实体 | **独立本体表** `neuops_ontology.db`（`o_*` 表），与现轨 `spare_mail_task` 互不读写 |
| 动作 | **动作注册表** `app/ontology/actions.py`（`ACTION_REGISTRY`，13 个动作），LLM 只能从中选取 |
| 邮箱凭据 | **DB 优先**：`employee_channels` 表（落在 `neuops_sessions.db`，非本体库）；env `ONT_MAIL_*` 兜底 |
| 调度 | `runtime.sync_scheduler()` 按启停状态幂等拉起/取消 asyncio 监听 task；`_ont_loop` 每 60s POST `run-full` |
| 与现轨关系 | 并行、零影响；emp-008 现轨不动，本体轨只读复用其 skill/tool，需修改处独立新建 |

**唯一共享事实源**：邮箱 IMAP。一封邮件只进一条轨道（按 `mode: legacy|ontology` 入口路由）。

> **本体三要素（实体/知识/动作）名义上已建模，但实际接线度有限**——默认运行时主控是 `orbit` 的硬编码状态机 + `execution` 的 `if` 分支，本体声明（`CONCEPTS`/`ACTIONS`/`RULES`）多为**文档性/展示性**，**仅 `use_llm=True` 时**才由 LLM 决策消费。真实接线度见 **§9 本体三要素真实运转度审计**。

---

## 2. 模块文件地图（实际，file:line 为当前版本）

| 文件 | 用途 | 关键函数 |
|---|---|---|
| `app/ontology/orbit.py` | 全流程编排核心 | `claim_inquiries`(SEEN 认领/建任务)、`process_replies`(入向回复归集)、`drive`、`run_full`、`ctx_from_task`、`_parse_quote`、`_thread_match`、`_strip_quoted`、`_supplier_mentioned_in`、`_deadline_passed`、`_maybe_remind_quotes` |
| `app/ontology/execution.py` | 治理开关 + 动作执行器 | `execute_action`、`set_governor`、`needs_exec`、`_employee_managed`、`_send_tpl` |
| `app/ontology/decision.py` | LLM/规则决策 | `build_fact_context`、`propose_action` |
| `app/ontology/engine.py` | 决策循环入口 | `decide_action`、`evaluate_task`、`run_alignment` |
| `app/ontology/ingest.py` | 邮箱事实采集 | `scan_window`、`_ont_participants`、`is_inquiry` |
| `app/ontology/mail_gateway.py` | 本体轨独立邮箱网关 | `_ont_mail_cfg`(DB 优先)、`send_mail`(cc 去重)、`mark_seen_by_message_id` |
| `app/ontology/mail_tpl.py` | A–G 模板渲染 | `reply_recipients`、`render` |
| `app/ontology/store.py` | `O_*` 表 CRUD + 两阶段认领状态机 | `upsert_email`、`try_claim_email`、`mark_email_claimed`、`mark_email_failed`、`pending_claim_mails` |
| `app/ontology/actions.py` | `ACTION_REGISTRY` 声明 | 13 个动作声明 |
| `app/ontology/knowledge.py` | 声明式规则层 | `KNO-R-01` 规则集、表达式求值 |
| `app/ontology/ontology.py` | 本体知识层 TBox/ABox/ACTIONS/INVARIANTS | `validate_action` |
| `app/ontology/routes.py` | HTTP 路由 | `/api/ontology-emp009/run-full`、`/governor`、`/close` |
| `app/ontology/runtime.py` | 调度运行时 | `sync_scheduler`、`_ont_loop` |
| `app/ontology/registration.py` | emp-009 注册 | `register_emp009` |
| `app/ontology/llm.py` | LLM 决策回路 | `llm_decide_action`、`validate_action` |
| `app/ontology/schema.py` | 本体轨 schema | `o_*` 表 DDL |

**员工/渠道配置（跨轨共用）**：`app/db/employees.py`（`db_get_employee_channel`/`db_set_employee_channel`/`db_list_employee_channels`/`db_get_employee`）、`app/db/schema.py`（`employees` `:190-202`、`employee_channels` `:207-216` 与 `:470-479`）。`employee_channels`/`employees` 表位于 **`neuops_sessions.db`**（不是本体库）。

---

## 3. 核心机制实现说明

### 3.1 认领去重（三层去重，防漏/防丢单/防误认领）
- **持久账本唯一键**：`o_email.email_message_id`（`store.upsert_email` PK）。
- **IMAP `\Seen` 握手**：建任务成功后才 `mark_seen`（`orbit.py:318-321`），未认领邮件不标已读，停机后可重扫。
- **恒等任务映射**：`task_id = OT-{md5(message_id)}`（`orbit._shake` `orbit.py:513-515`），upsert 覆盖而非新增。
- **两阶段消费**：`claim_status` ∈ {pending → done / failed}；建任务成功才置 done，失败置 failed 且 `continue`（单封坏邮件不中断整批）；`pending_claim_mails()` 从库还原重试，不依赖 IMAP 窗口。
- **发起人白名单**：`ONT_REQUESTERS`（`ingest._ont_participants`）；空=不限制；`.env`/`tests/conftest.py` 已隔离。`self_email` 排除自身，防模板 B 自我认领。
- **水位用途是"反的"**：`scan_window`（`ingest.py:124-143`）取 `min(now-ONT_SCAN_HOURS, 水位-1h)` 扩大下界**防漏**（停机 >48h 补扫）；`read_inbox` 失败不推进水位。

### 3.2 报价解析与比价
- `_parse_quote`（`orbit.py:154-185`）：抽取单价/货期/成色/数量；连单价都无 → 返回 `None` 走 `unparseable` 分支催补。
- **同供应商 upsert 去重**（`orbit.py:415-426`）：按 `email` 小写匹配 upsert，不再 append 产生旧价。
- **人工改价保护 `is_manual`**（`orbit.py:415-420`）：有手动改价的供应商忽略后续邮件报价（不覆盖、不重复）。
- **最低价规则**：智能体比价后固定选最低价（`agent_selected_supplier`，`orbit.py:253/395/430`），每次报价后重算。
- **审批覆盖规则**：审批人"确认采购"→ 沿用最低价；仅当审批人"显式点名【其他】供应商"且该家确已报价才覆盖（`_supplier_mentioned_in` `orbit.py:188-196`）。`target_supplier` 仅当审批人回复后才写入（`orbit.py:396`、执行器 `execution.py:266`），防止绕过审批门。

### 3.3 审批驳回
- `_REJECT_KW`（`orbit.py:15`）命中 → 置 `approval_rejected` → `decide_action` 返回 `abortTask` 中止（`CLOSED_ABORT`）。

### 3.4 抄送透传（inquiry_cc）+ E/G 主送修复
- **透传机制**：`ctx_from_task`（`orbit.py:245`）取 A 邮件全部抄送人 → `inquiry_cc`；B/D/E/F/G 发信均并入 `cc`（B `execution.py:155-156`；D `:191-196`；E `:177-180`；F `:237-242`；G `:221-224`）。
- **E/G 主送修复（2026-08-31）**：原 E/G 传 `reply_all_from=q.get("reply_all")`，触发 `mail_tpl.reply_recipients` 把原邮件 To+Cc+From 全部并进主送，导致观察者出现在主送。**修复后 E/G 主送严格=选中供应商，其余（发起人/审批人/观察者）一律 Cc**；线程连续性由 `reply_to`/`refs` 保证（`execution.py:172-180`、`:216-224`）。
- `send_mail` cc 去重（`mail_gateway.py:264-269`）：`dict.fromkeys` + 排除自身 + 已在主送的地址踢出 Cc，防自激循环。

### 3.5 员工渠道 DB 凭据（关键运维点）
- **009 读邮箱口令来自 `employee_channels` 表**（DB 优先，`_ont_mail_cfg` `mail_gateway.py:20-60`），命中 `address+pwd` 即用，否则回退 `ONT_MAIL_*`。
- **生产踩坑（已修）**：服务器 `.env` 的 `ONT_MAIL_PASSWORD` 为空，且 `employee_channels` 表**从未配置 emp-009 渠道** → 009 用空口令登不上 b4 收件箱、无法认领 A。已在服务器 `neuops_sessions.db` 写入 `emp-009/email`（address=biquanzhi4@163.com + 口令），持久化。
- emp-008 现轨同理走 `_proc_mail_cfg`（`mcp_tools.py:121-167`）。

### 3.6 运行时门控与启停（真实生效）
- `_employee_managed`（`execution.py:40-59`）：查 `db_get_employee("emp-009").enabled` + `skill_states`；未注册向后兼容放行。
- `needs_exec`（`execution.py:66-69`）= `mode∈(ontology,split) AND exec AND _employee_managed`。
- **页面开关即时拉起/停止线程**：`runtime.sync_scheduler()`（`runtime.py:43-56`）按 `should_run()` 幂等 create/cancel emp-009 的 asyncio task；页面 `PUT /api/employees/emp-009/enabled` 落库后立即调 `sync_scheduler()`。`main.py` lifespan 启动期 `register_emp009()` + `sync_scheduler()`，退出 `stop_now()`。

### 3.7 8 项缺口修复清单（均已落地 + 加测试）
| # | 缺口 | 落点 |
|---|---|---|
| 1 | 报价结构化解析 | `orbit._parse_quote` |
| 2 | 同供应商 upsert 去重 | `orbit.process_replies :415-426` |
| 3 | 审批驳回分支 → abortTask | `orbit._REJECT_KW` + `decision.py` |
| 4 | 最低价/点名覆盖/延迟写 target_supplier | `orbit.ctx_from_task`/`processApprovalDecision` |
| 5 | 线程匹配去坏表达式 | `orbit._thread_match :211-221` |
| 6 | 截止/临期提醒 | `orbit._deadline_passed`/`:518-548` |
| 7 | 人工改价保护 is_manual | `orbit :415-420` |
| 8 | 动作执行器补齐（含 requestMissingFields/requestTrackingNo/receiveSupplierQuote/finalizeQuoteCollection/manualCloseTask + `/api/ontology-emp009/tasks/{id}/close`） | `actions.ACTION_REGISTRY` + `execution.execute_action` |

---

## 4. 配置旋钮

**`app/config.py` 内定义：**
- `ONT_MAIL_USERNAME/PASSWORD/IMAP_*/SMTP_*/DISPLAY_NAME`（`:159-166`）：默认回退现轨 `PROC_MAIL_*`；双轨并行必须显式配置，否则抢同一收件箱。
- `ONT_SUPPLIERS`（`:169`）：`名称:邮箱,名称:邮箱` → `orbit.config()` 解析。
- `ONT_APPROVERS`（`:170`）：逗号分隔邮箱。
- `ONT_REQUESTERS`（`:174`）：发起人白名单；**空=不限制，生产务必配**。
- `ONT_SCAN_HOURS`（`:176`）：默认 `48`，扫描窗口下界小时数。
- `ONT_SETTLEMENT_ENABLED`（`:178`，默认 `0`/关闭）：**结算闭环总开关**。控制两件事：① 工程师发"更换完成"邮件是否触发闭环；② 是否向供应商发 G 结算邮件。当前业务不需要该闭环，**默认关闭、预留后续启用**——置 `1` 即恢复，无需改代码。

**仅运行时 `os.getenv` 读取（建议后续收口到 config.py）：**
- `ONT_SCHEDULER`（默认 `"1"`，`"0"`=禁自动调度总闸）
- `ONT_MODE`（默认 `"off"`，`off|legacy|ontology|split`）
- `ONT_EXEC`（默认 `"0"`，=`1` 真实发信/落库）
- `ONT_LLM`（默认 `"0"`）
- `ONT_ROLL`（默认 `0.0`）
- `ONT_SCHEDULER_USE_LLM`、`ONT_USE_LLM`（默认 `"1"`）
- `ONT_DB_PATH`（本体库路径，默认 `neuops_ontology.db`）

---

## 5. 测试与真实联调结果

### 5.1 单元测试（全部本地，57 例全绿）
| 文件 | 覆盖 |
|---|---|
| `test_ont_gaps.py` | 8 缺口 + 异常分支 + 供应商实名映射（15 例） |
| `test_ont_claim.py` | 认领去重/防漏/防丢单/防误认领（12 例） |
| `test_ont_emp009.py` | 注册/动作声明/决策提议/规则校验/审计/Governor |
| `test_ont_emp009_flow.py` | 全流程自走（FakeMG） |
| `test_ont_quote_strip.py` | 携带原文回复不干扰审批意图（`_strip_quoted` + 最低价，2 例） |
| `test_ont_cc_propagation.py` | 抄送透传 A→B/D/E/G；**E/G 主送仅供应商**（按主题精确匹配，防假阳性） |
| `test_ont_runtime.py` | 启停 `sync_scheduler` 幂等 |
| `test_ont_e2e_mock.py` | B→D→E→F→G 脱机集成 |
| `test_ont_ontology_layer.py` | 语义校验（LLM 提议须命中可执行动作） |
| `test_ont_llm_decision.py` | LLM 决策回路 |

> 单元测试假阳性已修复：`test_ont_cc_propagation` 早期用 `to==[S1] and cc 含观察者` 找 E，E 主送被 Reply-All 合并后误配到 G 造成"假通过"；现改为按主题（"订货确认"/"采购结束"）精确匹配 + `_assert_to_only` 断言主送恰好为供应商。

### 5.2 分布式联调（真实 163 邮箱 + 服务器 009 主脑）
驱动 `tests/ont_cotest_local_driver.py`：本地仅模拟 b1/b2/b5/b6 收发，决策与发信全由服务器 122.51.98.98:9007 的 009(b4) 完成。复跑前标准动作：**停 009 → 清 6 邮箱（直连 imap.163.com，代理隧道已废弃）→ 清 `neuops_ontology.db` 八张表 → 起 009**。

| 项目 | 配置 | 结果 |
|---|---|---|
| `PRJ-ONT-162132` | 不带观察者 | ✅ 全链路 B→D→E(b6 最低价)→F→G 跑通，EXPECT_CC 抄送正确、主送仅供应商 |
| `PRJ-ONT-162611` | 带 3 个一次性观察者（fengzhengyi/lihua/li.rg@neusoft.com），仅本次 | ✅ 全链路跑通，3 人随 A 抄送透传 B/D/E/F/G 全程可见 |

> **3 个观察者邮箱为一次性**：仅 `PRJ-ONT-162611` 那一次携带，跑完后已 `git checkout` 还原测试脚本（无任何提交残留，仓库内零引用）。后续测试不再携带。

---

## 6. 已知问题与后续优化待办（基线）

> 以下为截至 2026-08-31 已知的可优化项，按优先级/风险标注，供后续迭代。

### P1 — 正确性风险
1. **Reply-All 两套路径并存**：D/F/B 仍依赖 `mail_tpl.reply_recipients`（To 合并），E/G 已改为显式 To/Cc。不一致易再生"观察者进主送"类缺陷。**建议统一为"主送=业务对象、其余全 Cc + reply_to/refs 保线程"**，删除 Reply-All 的 To 合并分支。
2. **`employee_channels` 缺配无告警**：009 凭据缺失时 `run-full` 仍返回 200（异常被吞），表面"在跑"实际不干活（本次真实踩坑）。**建议**：凭据缺失/登录失败时显式告警（日志 ERROR + 健康端点 `claim-state` 置异常态）。
3. **`process_replies` 全量 `read_inbox(since 48h)`**（`orbit.py:338`）：任务多时重复拉取。**建议**按任务 `b_msg_ids` 收窄，或增量游标。

### P2 — 可观测 / 运维
4. **failed 邮件无自动告警**：`store` 有 `list_unclaimed_emails` 但无自动通知；长期 failed/卡住任务靠人工查。**建议**加阈值告警（如 failed> N 或任务卡某状态 > Xh 触发通知）。
5. **`drive()` 每轮全量 `list_tasks` + 串行 `upsert_task`**（`orbit.py:460-505`）：高并发下可考虑批量/增量。
6. **健康度端点覆盖**：9007 `/api/ontology-emp009/claim-state` 已有；建议补充"上次成功 run-full 时间 / 距截止最近任务 / failed 计数"面板。

### P3 — 配置与工程化
7. **旋钮散落**：多数本体轨旋钮在 `os.getenv` 而非 `config.py`，易漏配。**建议**收口到 `config.py` 集中定义 + 启动时校验必填项。
8. **`inquiry_cc` 无上限/无去重校验**：A 抄送过多观察者会带入所有后续邮件。**建议**加白名单/数量上限与去重。
9. **联调依赖真实外部邮箱**：`ont_cotest_local_driver.py` 需 6 个 163 口令 + 服务器可达，无 CI、易碎。**建议**抽象一个"FakeSMTP/FakeIMAP"适配器，让分布式链路也能在 CI 内跑（保留真实联调作为手动 smoke）。

### P4 — 功能扩展（非阻塞）
10. **双流一致性**：本体轨用单状态机，现轨双流（internal/external）未迁移；如后续需要可在 `invariant` 补双流一致规则。
11. **审批人/供应商实名映射**：当前靠 `mail_tpl.build_fields(supplier_names=)` 显示实名，建议把"邮箱↔业务主数据"映射固化进 `o_person` 并在 `ONT_SUPPLIERS/APPROVERS` 基础上补全。
12. **后台手动关闭/取消 + 审计外查询页**：本体轨已有 `manualCloseTask` + `/close` 端点，但 9006 侧运维域页面尚未接该能力。

---

## 7. 一键复跑手册（验证/回归用）

```bash
# 1) 停 009
ssh -i ~/.ssh/neuops_ci_deploy ubuntu@122.51.98.98 \
  'sudo systemctl stop neuops-9007; sleep 1'

# 2) 清 6 个 163 邮箱（直连，勿走废弃代理隧道）
SMOKE_IMAP_HOST=imap.163.com SMOKE_IMAP_PORT=993 \
  .venv/bin/python tools/clear_all_mailboxes.py
sleep 20   # 等 163 异步 expunge

# 3) 清服务器本体库八张表（用 cursor.rowcount；连接对象无 rowcount 属性）
ssh -i ~/.ssh/neuops_ci_deploy ubuntu@122.51.98.98 \
  'cd /home/ubuntu/neuops-agent-demo && python3 - <<PY
import sqlite3
c=sqlite3.connect("neuops_ontology.db"); cur=c.cursor()
for t in ["o_task","o_email","o_supplier_quote","o_audit_log",
          "o_alignment","o_session","o_scan_state","o_person"]:
    cur.execute("DELETE FROM "+t)
c.commit(); c.close()
PY'

# 4) 起 009
ssh -i ~/.ssh/neuops_ci_deploy ubuntu@122.51.98.98 \
  'sudo systemctl start neuops-9007; sleep 3; systemctl is-active neuops-9007'

# 5) 本地跑联调（需导出 MI1/MI2/MI3/MI5/MI6/B4 口令）
export MI1_PASS=... MI2_PASS=... MI3_PASS=... MI5_PASS=... MI6_PASS=... B4_PASS=...
.venv/bin/python tests/ont_cotest_local_driver.py
```

**务必先停 009 再清场**，否则 009 在清理窗口空跑会重认领残留邮件、造出新任务。

---

## 8. 追踪
- 行为契约：`specs/012-ontology-emp009/spec.md`（V0.1 规划）
- 设计：`specs/012-ontology-emp009/design.md`（V0.2 目标范式）
- 实现现状（本文）：`specs/012-ontology-emp009/IMPLEMENTATION.md`（V1.0）
- 影子验证留档：`specs/012-ontology-emp009/shadow-validation-report.md`

---

## 9. 本体三要素真实运转度审计（2026-08-31 整理）

> 目的：回答"实体/知识/动作这套本体逻辑，现在真的按它运转吗？"——给后续优化一个**诚实的接线度清单**，而不是只看文件名就以为已本体化。

### 9.1 默认运行时的真实主控链路

```
runtime._ont_loop (每 60s POST run-full, use_llm = ONT_SCHEDULER_USE_LLM=="1")   ← 默认 "0"
  └─ orbit.run_full → orbit.drive
       ├─ ctx_from_task(t)  → 事实 ctx(dict)
       ├─ _decide(ctx,t,False) → engine.decide_action(use_llm=False)
       │     └─ decision.propose_action  ← 【真实驱动】S1–S5 手写 if/elif 状态机
       │         └─ knowledge.check_target("createTask", ctx)  ← 规则引擎【仅这一条】被消费
       ├─ (默认) chosen = rule_act  → execution.execute_action(chosen, t, ctx)
       │     └─ if action_id == "..."  ← 【真实执行】execution.py 硬分支分派（非注册表）
       └─ (仅 use_llm=True) 才调 llm_decide_action → ontology.build_abox + ACTIONS + validate_action
```

**关键开关事实**：
- `runtime.py:33` `use_llm = os.getenv("ONT_SCHEDULER_USE_LLM","0")=="1"` → **默认 `False`**。
- `orbit.py:488` 始终先算规则基准；`orbit.py:495` `if shadow or (trusted and use_llm)` 才调 LLM；`orbit.py:507` 默认用规则动作执行。
- 即：**默认部署（009 生产）走纯规则式硬状态机，本体声明不参与决策**。`engine.decide_action` 注释写"LLM 提议 + 规则校验"，但只有 `use_llm=True` 才真正走 LLM 提议分支。

### 9.2 实体（Entity）—— 名义建模，无真实实体层

| 项 | 真实地位 |
|---|---|
| 真实实体 | SQLite `o_*` 表行（`o_task`/`o_email`/`o_supplier_quote`/…，`schema.py`+`store.py`）+ `internal_status`/`external_status` 两个状态字符串（`orbit.ctx_from_task` 把它们拼成 `ctx` dict） |
| `ontology.py:16-41` `CONCEPTS`/`RELATIONS`（TBox 领域概念/关系） | **纯文档性声明**。全局 grep 无任何运行时代码读取/实例化它；既不参与决策，也不做实体识别/消歧/链接。**仅在 `use_llm=True` 时作为语境喂给 LLM**（经 `llm.py` 间接引用 `ACTIONS`/ABox，不直接读 `CONCEPTS`） |
| 实体抽取/对齐代码 | **不存在**。没有把邮件/DB 行"实例化为本体实体对象"的逻辑 |

**结论**：所谓"本体实体"目前就是 DB 行 + 状态字符串，**没有真正的实体层**。CONCEPTS/RELATIONS 是设计文档的代码化，不参与运转。

### 9.3 知识（Knowledge）—— 规则引擎真存在，但只用了 1/11

| 项 | 真实地位 |
|---|---|
| `knowledge.py` 极小表达式求值器（`eval_node`/`validate`/`check_target`） | **真实可用**的代码资产 |
| `knowledge.py:86-131` `RULES`（11 条声明式规则：create_required / distribute_ready / finalize_quote / no_valid_quote_abort / submit_approval / approval_valid / order_ready / ship_no / ask_tracking / close_confirm …） | 声明齐全，但**运行时实际被调用的只有 `check_target("createTask", ctx)`**（`decision.py:70` + `execution.py:290`）。**其余 10 条规则从未被 `check_target` 消费** |
| `decision.py:68-129` `propose_action` 的 S1–S5 手写 `if/elif`（基于 `external`/`internal` 状态字符串） | **真正驱动流程的知识**。A→B→D→E→F 全链路实际由这段硬编码状态机推进 |

**结论**：知识层是**双轨并存**（架构债）：
- 一套声明的 `knowledge.RULES`（只用了 createTask 一项，且仅作"缺字段→requestMissingFields"的前置判断）；
- 另一套手写 S1–S5 状态机（`decision.py`）才是实际大脑。
两者规则有重叠但不完全一致；S1–S5 的优先级/边界才是生产行为的最终解释。

### 9.4 动作（Action）—— 注册表纯展示，语义规范仅 LLM 模式生效

| 项 | 真实地位 |
|---|---|
| `actions.py:7-72` `ACTION_REGISTRY`（13 个动作） | **纯展示性**。全局 grep 仅 `routes.py:31,56` 的 HTTP 端点导出（给前端看"有哪些动作"）。**运行时动作分派完全不走它** |
| `ontology.py:46-145` `ACTIONS`（带 `条件/效果/不变量/幂等` 语义规范）+ `validate_action` | **仅 `use_llm=True` 时**由 `llm.py:85,94` 喂给 LLM 做提议 + 裁决。**默认运行时不被读取、不被校验** |
| `execution.py:148-349` `execute_action` 的 `if action_id == "..."` 硬分支 | **真实动作执行器**。13 个动作分支已补齐（含 requestMissingFields/requestTrackingNo/receiveSupplierQuote/finalizeQuoteCollection/manualCloseTask 等） |

**结论**：动作的"本体语义声明"（效果/不变量/幂等）在默认运行时是**文档性的，未被校验器强制**——`action_id` 字符串就是契约，靠 `execution.py` 里的 `if` 分支实现。唯一被强制的语义约束是 createTask 经 `knowledge.check_target` 间接校验一次。

### 9.5 一句话结论 + 对优化的含义

- **本体三要素代码都写齐了**（`ontology.py`/`knowledge.py`/`actions.py`），但**默认运行时它们是"纸面本体 + 局部钩子"**：实体=DB 行、知识=手写 S1–S5、动作=if 分支。
- **这反而解释了为什么之前联调全链路能跑通（A→F 真实可用）**——因为它根本不依赖本体声明，靠的是 `orbit`+`decision`+`execution` 的硬逻辑。
- **"本体化"真正生效的唯一入口是 `use_llm=True`**（设 `ONT_SCHEDULER_USE_LLM=1` 或 `ONT_LLM=1` 且 `use_llm` 透传）：此时 LLM 读 ABox + `ACTIONS` 语义规范 + `validate_action` 裁决，`knowledge.RULES` 更多规则也能介入。但默认 009 部署未开启。
- **后续优化含义**（对应 §6 P1–P4）：若要让"本体"真正当家，应①把 `decision.py` 的 S1–S5 与 `knowledge.RULES` 收敛为单一规则源（消除双轨）；②让 `execution.execute_action` 经 `ACTION_REGISTRY`/`ACTIONS` 分派并对不变量做前置校验（消除"声明≠执行"）；③实体层若要落地，需补实体识别/状态机收敛，而非仅靠 `ctx_from_task` 拼 dict。否则"本体"目前只是高质量的设计文档。

---

## 10. 本体地基增强：拓扑与一致性面板（2026-08-31 落地）

> 目的：把 §9 的"纸面本体"审计**可视化、可交互、可自检**。在 9006「本体可观测」页面新增「拓扑与一致性」子面板，让本体定义从"字典"变成"图 + 映射 + 一致性校验"三件套，供后续打地基时对照。
> 原则：用户要求"先别着急跑，先打好地基"——本增强**零新后端、不部署、不跑流程**，仅交付页面 + 离线预览供审查。

### 10.1 交付物与位置

| 文件 | 角色 |
|---|---|
| `contract-compare-9006/frontend/procurement.html` | 子菜单「🕸 拓扑与一致性」+ 面板 HTML（概念×关系图 / 动作-状态映射图 / 一致性校验三块） |
| `contract-compare-9006/frontend/procurement.app.js` | `loadOntTopology()`：拉 `/spec` → 归一化小写键→大写键 → `window.OntTopo.buildAll(spec)` 渲染 |
| `neuops-agent-demo/ont_topo_build.js` | **纯字符串 SVG 渲染器**（无 DOM 依赖，node/浏览器共用）：`conceptGraph`/`actionMap`/`health`/`buildAll` |
| `neuops-agent-demo/ontology_foundation_preview.html` | 单文件离线预览（内嵌真实抽取定义 + 渲染器），**不启动服务即可看地基现状** |

数据链：9006 `frontend` → `GET /api/ontology/spec`（9006 `backend/ontology_gateway.py` 转发/缓存 9007 `/api/ontology-emp009/spec` 或 AST 回落）→ 返回 TBox（CONCEPTS/RELATIONS/ACTIONS/INVARIANTS/RULES/ACTION_REGISTRY）。**复用既有网关，零新后端**。

### 10.2 三件套渲染逻辑

1. **概念×关系图（radial）**：解析 `RELATIONS` 的 `dom.rel(range)` 签名→边；`ALIAS` 把 `task→InquiryTask` 等映射；`resolve` 仅接受合法概念 id（丢噪声 token）；`isolated`=无任何关系连接的概念（红圈虚线一眼可见）。
2. **动作-状态映射图（bipartite）**：左列状态（来自 RULES `eq` 前置 + ACTION_REGISTRY `next_*` 后继，按 `STATUS_ORDER` 排序），右列动作；前置边=规则要求的前置状态，后继边=注册表写入的状态。
3. **一致性校验（health）**：声明↔注册、规则悬空、状态词表漂移、声明↔执行漂移四类静态比对。

### 10.3 地基现状（渲染器实测，2026-08-31）

抽取真实定义：CONCEPTS 12 / RELATIONS 10 / ACTIONS 14 / INVARIANTS 4 / RULES 11 / ACTION_REGISTRY 13。

**① 6 个孤立概念（无任何关系连接，图上红圈）**
`Engineer`、`Part`、`InquiryEmail`、`Approval`、`Order`、`Settlement`。对应概念图 12 节点 / 7 边——它们只出现在 `CONCEPTS` 字典里，没有任何 `RELATIONS` 把它们与 `InquiryTask`/`Supplier`/`Quote` 关联（如 `Order` 只被 `confirmOrderToSupplier` 动作语义描述，关系表里无对等连接）。

**② 孤儿声明：`requestQuoteClarification`**
在 `ontology.py:131` 的 `ACTIONS` 里声明了完整语义（条件/效果/不变量/幂等），但 `actions.py` 的 `ACTION_REGISTRY`（13 项）**不含它** → 运行时不注册、不被 `execution.execute_action` 分派、不被任何决策路径调用。即"文档里有、代码里跑不到"。

**③ 状态词表漂移（规则前置 vs 注册表后继不一致，动作→状态链在图上断开）**
- 规则 `order_ready`（`knowledge.py:119`）：前置 `eq external_status=R_ORDER`；但 `confirmOrderToSupplier` 注册表（`actions.py:45`）后继写 `ORDER_CONFIRM`。
- 规则 `ship_no`/`ask_tracking`（`knowledge.py:123/126`）：前置 `eq external_status=R_ORDER`；但 `receiveTrackingNumber` 注册表（`actions.py:50`）后继写 `WAIT_ENGINEER_CLOSE`。
- 规则 `close_confirm`（`knowledge.py:129`）：前置 `eq external_status=R_WAIT_ENGINEER_CLOSE`；但 `engineerFinalClose` 注册表后继写 `R_SETTLE`。

→ 规则侧用 `R_ORDER`/`R_WAIT_ENGINEER_CLOSE`（带 `R_` 前缀、内部流命名），注册表侧用 `ORDER_CONFIRM`/`WAIT_ENGINEER_CLOSE`（无前缀、外部流命名），两边词表不交，二分图上出现"悬空前置节点"。

**④ 声明↔执行漂移（声明式规则 11 条仅 1 条被运行时消费）**
`knowledge.check_target` 实际仅被 `decision.py:70` + `execution.py:290` 以 `target="createTask"` 调用一次（§9.3 已确认）。其余 10 条规则（`requestMissingFields`/`distributeInquiry`/`finalizeQuoteCollection`/`abortTask`/`submitApproval`/`processApprovalDecision`/`confirmOrderToSupplier`/`receiveTrackingNumber`/`requestTrackingNo`/`engineerFinalClose`）从不被 `check_target` 消费，流程由 `decision.py` 的 S1–S5 硬编码状态机驱动。知识层"声明"与"执行"是两套并行体系。

> 另：health 还标出 9 个注册表后继状态（`R_FR02_MISSING_FIELDS`/`R_SEND`/`INVITE_QUOTE`/`QUOTE_COLLECT_DONE`/`ORDER_CONFIRM`/`WAIT_ENGINEER_CLOSE`/`R_SETTLE`/`CLOSED_ABORT`/`CLOSED_MANUAL`）未被任何规则前置引用——多为终态/过渡态，属"单向出口仅展示"，风险低于③④。

### 10.4 打牢地基的下一步（与 §6 / §9.5 呼应，按低成本→高收益排序）

1. **补概念关系（消①）**：把 6 个孤立概念接回 `RELATIONS`（如 `Engineer submittedBy`、`Part describedBy`、`task.orders(Order)`、`task.settles(Settlement)` 等），让实体图闭合——纯声明、零运行风险。
2. **收敛状态词表（消③）**：统一 `R_ORDER` 与 `ORDER_CONFIRM`、`R_WAIT_ENGINEER_CLOSE` 与 `WAIT_ENGINEER_CLOSE` 为同一组状态常量（建议落到 `ontology.py` 的 `STATUS` 枚举），规则前置与注册表后继引用同一来源。
3. **统一声明与执行（消②④）**：让 `execution.execute_action` 经 `ACTION_REGISTRY` 分派并对 `ACTIONS` 不变量做前置校验——把 `requestQuoteClarification` 补进注册表，并让 `knowledge.check_target` 覆盖全部动作（消除"双轨"）。
4. **实体层落地（可选）**：若要让"本体"真正当家，补实体识别/`ctx_from_task` 收敛，而非仅靠 DB 行 + 状态字符串（§9.5③）。

> 当前默认部署 `ONT_SCHEDULER_USE_LLM=0`，以上漂移不影响 A→F 实际跑通（靠硬逻辑）；但要让"本体化"成为真实主控，①②③是必须先填的坑。

