# 备件询价智能体 · 本体化（LLM 自主决策）设计文档 V0.2

> 状态：**迭代中（已落地本体知识层 + LLM 决策回路 + 影子对齐；详见下方留档）**
> 目标范式：把当前的"邮箱驱动的过程式状态机"重构为"独立的本体轨"，以"实体 + 知识/规则 + 动作注册表"为底座，由 LLM 在规则约束内做自主决策；新轨与现轨并存、灰度收敛、跑通后替换。
> 说明：**不是缝补现表，而是独立自建一套本体轨道**；唯一共享的是"邮箱唯一事实源"。
>
> 数字员工决策：**新建 emp-009** 走本体轨。skill/tool 允许"只读复用"现轨；**一旦需要修改则绝不允许改动现轨文件，必须独立新建**，以零影响现有 emp-008。
>
> 📁 **留档**：实现与影子验证见 `specs/012-ontology-emp009/shadow-validation-report.md`

---

## 0. 定位与边界

| 维度 | 现轨 Current (现状) | 本体轨 Ontology (目标) |
|---|---|---|
| 决策主体 | 过程式 `_step_*` 函数 + 正则 + 少量 LLM 兑底 | LLM 在"动作集 + 规则约束"内自主决策 |
| 业务规则位置 | 硬编码在函数体里 | 声明式的知识/规则层（前置/后置/不变量） |
| 实体 | 单张 `spare_mail_task` + JSON 内嵌 | 独立本体表 + 显式关系 |
| 动作 | 函数即能力，无注册 | 动作注册表（语义/前置/后置/效果，可被 LLM 选） |
| skill / tool | 现有 `skill-proc-mail-inquiry`、`tool_send_mail` 等 | 允许 **只读复用**；一旦需要修改 → **必须独立新建**（不碰现轨文件，零影响 emp-008） |
| 依赖 | 单表读写 | 独立 schema，与现轨互不读写对方状态 |

**并存的唯一交界点**：邮箱 IMAP（唯一事实源）。通过入口路由/分流决定一封邮件走现轨还是本体轨。

---

## 1. 想解决的根本问题

现状不是"缺审计、缺表"，而是范式问题：
1. 业务规则散落硬编码在 `_step_parsing / _step_waiting_quotes / _mi_internal_wait_approval` 等函数里（[routes_procurement_agent.py](../../app/routes_procurement_agent.py)），新智能体无法复用这套"领域逻辑"，只能照抄/重写。
2. 每次新增分支、异常场景都要改函数体，维护成本随智能体数量上升。
3. 目标是为"将来更多智能体"树立一套**可共享、可推理、可约束**的领域底座。

---

## 2. 本体轨三层模型

核心："实体（有什么）— 知识/规则（约束、进而驱动）— 动作（做什么）"。

### 2.1 实体层（Ontology）

独立于 `spare_mail_task` 新建关系型本体表：

| 实体 | 唯一键 | 关键属性（示意） |
|---|---|---|
| Session 预会话 | sessionId | initiatorPerson、threadId、status(PRE_CHECK/CONVERTED/ABANDONED)、abandonReason、autoAbandonThresholdHours=24 |
| Task 任务 | taskId | derivedFrom、spareInfo、urgencyRaw、quoteDeadline、targetSupplierList、targetSupplier、trackingNumber、closeFeedback、status |
| Person 人员 | personId | name、email、role(engineer/approver/supplierContact)，**映射业务主数据** |
| Email 邮件 | emailMessageId | title、body、sendTime、templateType(A/B/C/D/E/G)、幂等键 |
| SupplierQuote 报价 | quoteId | belongTask、supplierContact、quoteRawText、receiveTime、isTimeout、isValid、invalidReason |
| AuditLog 审计 | auditLogId | bizType、bizId、action、operator、operateTime、contentSnapshot、remark（仅追加） |

关系：`Session contains Email`、`Task derivedFrom Session`、`Task has SupplierQuote`、`Task generate Email`、`Email belongTo Task`、`Person initiate Session`。

> 关键理解：实体层不是"给现表加字段"，而是**一套全新的 schema + 关系**。决策、追溯、扩展都建立在它之上。

#### 2.1.1 本体轨 Task 表（独立根实体）

**注意**：以下 Task 表与现轨的 `spare_mail_task` **是完全两张独立的表**——本体轨不读写现轨那张表，各自保存自己的任务状态。本体轨 Task 是整个本体的**业务根实体**，taskId 对外暴露给所有业务邮件。

| 字段 | 说明 |
|---|---|
| taskId | 全局唯一，对外暴露 |
| sessionId | 溯源：由哪个预会话转正（derivedFrom Session） |
| spareInfo | 备件信息（类型/品牌/PN/规格/成色/数量） |
| urgencyRaw | 原始紧急时长串（如 `5H`/`3MN`/`2D`） |
| quoteDeadline | 由 urgencyRaw 换算出的询价截止时间 |
| targetSupplierList | 本次询价目标供应商（映射 Person） |
| targetSupplier | 最终选定供应商（审批后写入） |
| trackingNumber | 供应商发货快递单号 |
| closeFeedback | 工程师最终反馈原文 / 关闭原因 |
| status | 任务状态（见下） |
| createTime / closeTime | 创建 / 关闭时间 |

**Task 状态机**（本体轨单一状态机，区别于现轨的双流状态）：

```
INIT → INVITE_QUOTE → QUOTE_COLLECT_DONE → APPROVAL_WAIT → ORDER_CONFIRM → WAIT_ENGINEER_CLOSE → CLOSED
   └────────────▶ CLOSED(abort，无有效报价 / 全部拒绝)          └────────────▶ CLOSED(工程师确认 / 后台手动关闭)
```

| 状态 | 含义 |
|---|---|
| INIT | Session 转正生成 Task，待分发询价 |
| INVITE_QUOTE | 询价中，等待供应商报价 |
| QUOTE_COLLECT_DONE | 报价收集完成（全部回复 或 到截止） |
| APPROVAL_WAIT | 等待审批人选择供应商 |
| ORDER_CONFIRM | 已向选定供应商下发订货邮件 |
| WAIT_ENGINEER_CLOSE | 已拿到运单号，线下黑盒，等待工程师最终反馈 |
| CLOSED | 任务闭环（正常完成 / 业务中止 / 手动关闭/取消） |

> 取舍：本体轨用**单状态机**表达主链路；现轨的双流 internal/external 作为"邮件实践"保留在现轨，不迁移进本体轨的状态机（本体轨面向 LLM 决策，主链路清晰优先）。如后续需要，可在 `invariant` 里补充双流一致性规则。

### 2.2 知识层（Knowledge / Rules）—— **本次最要补齐的一环**

把现在藏在 `_step_*` 函数里的领域逻辑，抽取为声明式、LLM 可读可校验的规则。规则三形态：

- **前置条件 precondition**：某动作可执行的前提（如"报价已有效后才 submitApproval"）。
- **后置断言 / 不变量 invariant**：某动作执行后必须满足（如"targetSupplier ⊆ validQuotes"、"快递单号非空才 WAIT_ENGINEER_CLOSE"）。
- **业务规则 rule**：领域公理（紧急时长换算、收集终止判据、线程/幂等匹配）。

待抽规则清单（对应现状函数，均为目前硬编码的逻辑）：

| 现状函数（目前硬编码） | 应抽成的声明式知识 |
|---|---|
| `_step_parsing` L2768：字段校验 R-FR-02、缺字段拒绝 | Rule: `createTask 需 requiredFields 齐全`；缺则动作 `requestMissingFields`（不建任务）|
| `_step_parsing` L2792-2799：Re:/ In-Reply-To 排除 | Rule: `发起识别`（有 in_reply_to/references 或 Re: 前缀 → 非发起，转线程处理）|
| `_step_sending_b` L3055：供应商名单 | Person 映射规则：`供应商来自业务主数据，不由工程师提供` |
| `_inquiry_deadline` L2834：紧急时长 → 截止 | Rule: `quoteDeadline = 发件时间 + 紧急时长`；解析失败用兕底 |
| `_step_waiting_quotes` L3202：Thread 匹配报价、超时/无效 | Rule: `报价匹配按 Thread/Message-ID`；`isValid`、`isTimeout` 判定 |
| 报价收集终止（全部回复 ∪ 到截止） | Invariant: `QuoteCollectionEnd := 全有效报价 ∪ 已到 deadline` |
| `_step_deciding_lowest` L3491 / `_mi_internal_send_d` L3688 | Rule: `D 汇总邮件提示最低价，含报价明细，抄送审批人+系统抄送` |
| `_mi_internal_wait_approval` L3798：审批选供应商 | Precondition: `targetSupplier ∈ validQuotes`；非法回信通知重选 |
| `_step_ordering` L3593：订货邮件 E | Action 效果: 携带地址/数量/原报价；提交后 `targetSupplier` 生效 |
| `_mi_step_wait_shipping` L4034：运单号 | Invariant: `拿到单号 → WAIT_ENGINEER_CLOSE（黑盒）`；无单号 → `requestTrackingNo` 主动索取 |
| 双流 internal/external 并行 | 关系约束: 内部流 `engineer→approve→confirm`、外部流 `quote→order→ship→settle` |
| 工程师最终确认 → G 结算 | Rule: `工程师反馈测试完成才 CLOSED`；G 携带单号/到货/验收全量 |

> 知识层是"让 LLM 决策有依据、可约束、可收敛"的核心，也是与现状最大的补差项。

### 2.3 动作层（Action Registry）

把当前每个能力函数**重新注册为动作**，带语义元数据，供 LLM 在当前状态（事实）下选择：

| 动作 | 对应现函数 | 前置(precondition) | 效果(postcondition) | LLM 可调 |
|---|---|---|---|---|
| requestMissingFields | `_reply_missing_fields` L3027 | requiredFields 缺失 | 回信指出缺项、不建任务 | ✅ |
| createTask / convertSessionToTask | `_step_parsing` 建任务段 | requiredFields 齐全 | Task 建立、生成 taskId/deadline | ✅ |
| distributeInquiry | `_step_sending_b` L3055 | Task 已建、有目标供应商 | 发 B 询价、外部流 → INVITE_QUOTE | ✅ |
| receiveSupplierQuote | `_step_waiting_quotes` 解析段 | 收件匹配 B 线程 | 生成 SupplierQuote、标记 isValid/isTimeout | ✅ |
| finalizeQuoteCollection | 收集终止段 | 全回复 ∪ 到截止 | 进入报价完成 | ✅ |
| submitApproval | `_step_deciding_lowest`/`_mi_internal_send_d` | ↑ 有有效报价 | 发 D 汇总审批、内部流 → APPROVAL_WAIT | ✅ |
| processApprovalDecision | `_mi_internal_wait_approval` L3798 | ↑ D 已发 | 校验合法 → 选中 targetSupplier | ✅ |
| confirmOrderToSupplier | `_step_ordering` L3593 | targetSupplier 已定 | 发 E 订货、外部流 → ORDER | ✅ |
| receiveTrackingNumber | `_mi_step_wait_shipping` L4034 | ↑ E 已发 | 记录单号 → WAIT_ENGINEER_CLOSE | ✅ |
| engineerFinalClose | 工程师确认段 | 工程师反馈测试完成 | 发 G 结算、CLOSED | ✅ |
| abortTask / requestTrackingNo | 中止/索取单号段 | 无有效报价 / 无单号 | 任务中止 / 回信索取 | ✅ |
| manualCloseTask | 后台（待定） | 有权限操作员 | 手动关闭+审计 | （新）✅ |

LLM **只允许**在以上动作集里选，不得自造动作或自由改参（参数由关联的 tool 约束）。

---

## 3. LLM 决策 + 规则校验循环（让"加规则"替代"改代码"）

```
                    邮箱(唯一事实源) ── 增量拉取
                          │
                本体状态投影(实体/关系加载)
                          │
      ┌───────────────────┴──────────────────────┐
      ▼                                            ▼
  现轨: spare_mail_task 状态机           本体轨: LLM 决策层(新入口)
   (存量任务继续, 保留兕底/回退)            读当前事实 → 从动作注册表选1个动作
                                                      │
                                         规则校验引擎(前置/后置/不变量)
                                                      │
                                     不满足 → 拒绝 + 返回原因给 LLM 重选
                                                      │
                                     满足 → 执行动作(tool) → 写回本体真实
                                                      │
                                         追加 AuditLog(append-only)
```

- **正确性 = 骨架(实体+动作) + 规则约束层**，二者恒定，靠**增补规则**收敛 LLM 决策，直至偏差为 0。
- 错误处理范式：跑挂一条 → 加/收紧一条规则 → 重跑 → 全过。**规则是"声明式"的新增，不是改函数体**。

---

## 4. 与现轨并存 / 灰度 / 替换

### 4.1 并存原则
- **两套表、两套状态、互不读写对方**：本体轨独立 schema；现轨 `spare_mail_task` 不动。
- **入口路由**：同一封邮件只进一条轨道。可用任务/账户级标记 `mode: legacy|ontology` 判断归属，防止双引擎处理同一任务。

### 4.2 三阶段演进

| 阶段 | 内容 | 风险 | 守门标准 |
|---|---|---|---|
| A. 只读对照 | 本体轨监听现轨任务，读邮箱推理"该走哪步"，**不落库不执行**，与现轨实际结果对比 | 0 | 决策与现状 **100% 对齐** |
| B. 灰度接管 | 新任务 / 新动作开启 LLM 决策，规则引擎兕底；存量任务走现轨 | 中 | 新轨测试全过、可回退 |
| C. 整体替换 | 入口切换到本体轨，现轨降为参照/兜底 | 高 | 全量 e2e 回归通过 |

### 4.3 关键点
- 同一份邮箱事实源、任务级 `mode` 标记、共用规则校验引擎（新引擎因此天然有约束可收敛）。
- 现有 `test_mail_inquiry_e2e.py` / 异常用例，直接作为新轨验收标准。

---

## 5. skill / tool 与数字员工（emp-009）

### 5.1 skill / tool 复用规则（硬约束）
- **允许只读复用**现轨的 skill/tool（如 `tool_send_mail`、`skill-proc-mail-inquiry`）——即"照原样拿来用、不改动"。
- **一旦需要修改现轨的 skill/tool ⇒ 绝不允许**：不修改现轨文件、不影响现 emp-008。必须**独立新建**新轨自己的 skill/tool。
- 因此新轨初版本质上是：**能只读复用的直接用，需要改的另起新文件**；被复用的现轨文件保持只读、零改动。

### 5.2 新轨 skill/tool（按需新建）
- **skill**：`skill-ont-proc-inquiry`（决策能力声明：预估会使用的动作/知识）、预会话技能等。独立于现有 `skill-proc-mail-inquiry.json`。
- **tool**：`sendMail`、`readInboxThread`、`parseQuote`、`selectApproval`、`storeTrackingNo`…… 每个 tool 携带签名 + 前置/后置条件声明，供规则校验引擎。
- 大模型只做**决策与编排**；时长换算、最低价计算、持久化、邮件网关等**确定性能力放 tool/代码**，不让 LLM 自由发挥。

### 5.3 数字员工：新建 emp-009
- 本体轨由**新的 emp-009** 承接（不改造现 emp-008）。
- emp-009 挂载：新轨的本体决策层 + 上述 skill/tool（只读复用的 or 新建的），面向同一业务语义但走本体决策。
- emp-008（现轨）保持现状与生产任务照跑，二者并行、互不影响。
- 轨道路由（如需）：邮件凭任务/账户 `mode` 判定归 emp-008 还是 emp-009；未开启前新轨先只读对照。

---

## 6. 落地清单（后续按此拆任务）

1. **本体 schema**：新建本体表（Session/Task/Person/Email/SupplierQuote/AuditLog）+ 关系；独立于现表。
2. **知识规则层**：抽取并声明 §2.2 的全部规则（前置/后置/不变量/业务规则）。
3. **动作注册表**：把现函数映射为 §2.3 动作，补语义元数据。
4. **规则校验引擎**：动作选择校验 + 拒绝原因回传。
5. **LLM 决策层**：读事实→选动作→执行→写回→审计的循环；新入口 + `mode` 路由。
6. **skill + tool**：能只读复用则直接复用；需修改则独立新建（不碰现轨）。
7. **数字员工 emp-009**：新建，挂载新轨决策 + skill/tool，与 emp-008 并行。
8. **阶段 A 只读对照**：对齐率守门。
9. **阶段 B/C 灰度与替换**。
10. **回归**：复用现有 e2e + 异常用例作为"无 bug 收敛"标准。

---

## 7. 不做 / 边界
- 本版**不重建现轨**、不改 `spare_mail_task`。
- 本轨为**独立新工程/新模块**，先求"干净、可共享"，不求一步替换。
- 后台手动关闭/取消、审计乱外查询页：作为未来扩展点，不影响本体轨骨架。

---

## 附录：现状关键代码索引（供回溯）
- 决策/状态机主入口：[routes_procurement_agent.py](../../app/routes_procurement_agent.py)
- 邮件能力（send/read/replyall）：[mcp_tools.py](../../app/mcp_tools.py)
- 现轨存储（扁平表+JSON）：[db/spare_mail.py](../../app/db/spare_mail.py)、[db/contract_mail.py](../../app/db/contract_mail.py)、[db/schema.py](../../app/db/schema.py)
- 现有技能：`skills/skill-proc-mail-inquiry.json`、`skills/skill-proc-chat.json`
- 现有测试：`tests/test_mail_inquiry_e2e.py`、`tests/test_mail_inquiry_abnormal.py`、`tests/mail_e2e_runner.py`