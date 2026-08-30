# NO-012 本体化（LLM 自主决策）数字员工 emp-009 — 行为规格

> Document Version: V0.1（行为契约草稿）
> Date: 2026-08-30
> Component: emp-009 + 本体轨（本体表 + 知识规则层 + 动作注册表 + 规则校验引擎 + LLM 决策层）
> Status: 规划中（设计见同目录 `design.md`；本文件为可验证行为契约）
> 依赖既有行为契约：NO-011 备件邮件询价（本规格不重复，引用其业务语义，但**运行于独立本体轨，不读写 `spare_mail_task`**）

## Purpose

为"将来更多智能体"建立一套**基于本体的 LLM 自主决策轨道**：以「实体 + 知识/规则 + 动作注册表」为底座，由 LLM 在规则约束内自主选定并执行动作；新轨与现轨并存、灰度收敛、跑通后替换。本契约定义本体轨的**可验证行为**，并承诺对现轨零影响。

关键范式：**正确性 = 骨架（实体+动作） + 规则约束层**；靠**增补声明式规则**收敛 LLM 决策偏差（等价于传统开发的"调无 bug"），而非修改过程式函数体。

## 边界与并存承诺

- 本体轨 MUST 使用**独立 schema**（本体表），MUST NOT 读写现轨 `spare_mail_task` / `spare_mail_config`。
- 本体轨与现轨 SHALL 共享唯一事实源：邮箱 IMAP（增量拉取）。
- 同一封邮件 MUST 只进入一条轨道；以任务/账户级 `mode: legacy|ontology` 判定归属，MUST NOT 双引擎处理同一任务。
- 数字员工：新建 **emp-009** 承接本体轨；现 emp-008 保持现状并行，MUST NOT 被修改。
- skill/tool 复用硬约束：现轨 skill/tool 允许**只读复用**；一旦需要修改，MUST 独立新建新轨文件，MUST NOT 改动现轨文件。

## 本体实体与关系

### Requirement: 本体实体模型（OBJ-R-01）
本体轨 SHALL 具备以下实体及其唯一键：
- `Session`（sessionId）— 预会话，PRE_CHECK/CONVERTED/ABANDONED
- `Task`（taskId，业务根实体，对外暴露）— 独立于 `spare_mail_task`
- `Person`（personId）— engineer/approver/supplierContact，SHALL 映射业务主数据
- `Email`（emailMessageId）— 幂等唯一键
- `SupplierQuote`（quoteId）— 标记 receiveTime/isTimeout/isValid/invalidReason
- `AuditLog`（auditLogId）— 仅追加（MUST NOT 修改/删除）

关联：
- `Session contains Email`
- `Task derivedFrom Session`（Session 转正生成 Task；历史邮件保留在 Session，不迁移关联）
- `Task has SupplierQuote`
- `Task generate Email`、`Email belongTo Task`
- `Person initiate Session`

#### Scenario: 独立 Task 表（OBJ-R-01）
GIVEN 现轨存在 `spare_mail_task`
WHEN 本体轨创建任务
THEN 该任务写入本体轨独立 Task 表，且 MUST NOT 影响现轨 `spare_mail_task` 数据

### Requirement: Task 单状态机（OBJ-R-02）
本体轨 Task SHALL 使用单状态机：`INIT → INVITE_QUOTE → QUOTE_COLLECT_DONE → APPROVAL_WAIT → ORDER_CONFIRM → WAIT_ENGINEER_CLOSE → CLOSED`；允许异常分支直入 `CLOSED`（无有效报价 / 全部拒绝 / 后台手动关闭）。

#### Scenario: 状态推进（OBJ-R-02）
GIVEN 任务处于 ORDER_CONFIRM 且已收到快递单号
WHEN 单号落库
THEN 状态流转至 WAIT_ENGINEER_CLOSE

## 知识层（声明式规则）

### Requirement: 规则三形态（KNO-R-01）
本体轨 SHALL 将领域逻辑表述为可校验的声明式规则，分为：**precondition**（动作前置）、**invariant**（状态不变量）、**rule**（领域公理）。这些规则 MUST 至少覆盖：
- `createTask` 需 requiredFields 齐全（缺则走 `requestMissingFields`，不建任务）
- 发起识别：带 in_reply_to/references 或 `Re:` 前缀的邮件为非发起，转线程处理
- 供应商名单来自业务主数据，不由工程师提供
- `quoteDeadline = 发件时间 + 紧急时长`；解析失败用兜底，流程不中断
- 报价按 Thread/Message-ID 匹配；`isValid`/`isTimeout` 判定
- 收集终止 := 全有效报价 或 到截止
- 审批合法性：`targetSupplier ⊆ validQuotes`；非法回信通知重选
- 拿到单号 → WAIT_ENGINEER_CLOSE（黑盒）；无单号 → requestTrackingNo 主动索取
- 工程师反馈测试完成才 CLOSED

#### Scenario: 规则拒绝非法动作（KNO-R-01）
GIVEN 审批人选了不在有效候选池的供应商
WHEN LLM 选择 `processApprovalDecision` 并提交该供应商
THEN 规则校验 MUST 拒绝该动作，并向审批人回信通知重新选择

### Requirement: 规则是唯一收敛机制（KNO-R-02）
LLM 决策偏差 MUST 通过**新增/收紧声明式规则**来消除，MUST NOT 通过修改过程式函数体。任何动作的执行 MUST 先通过规则校验引擎。

## 动作注册表

### Requirement: 动作集合（ACT-R-01）
本体轨 SHALL 将决策能力声明为固定动作集，LLM 只能从中选择，MUST NOT 自造动作或自由改参（参数由关联 tool 约束）。动作至少包含：
`requestMissingFields`、`convertSessionToTask`/`createTask`、`distributeInquiry`、`receiveSupplierQuote`、`finalizeQuoteCollection`、`submitApproval`、`processApprovalDecision`、`confirmOrderToSupplier`、`receiveTrackingNumber`、`engineerFinalClose`、`abortTask`、`requestTrackingNo`、`manualCloseTask`（后台，需权限）。

每个动作 SHALL 携带：语义、precondition、postcondition/effect。

#### Scenario: 动作受限选择（ACT-R-01）
GIVEN 任务处于 INVITE_QUOTE
WHEN LLM 被请求决策下一步
THEN LLM 只能在「receiveSupplierQuote / finalizeQuoteCollection」等前置满足的动作中选取

## LLM 决策与规则校验循环

### Requirement: 决策-校验-执行-写回（DRV-R-01）
本体轨 SHALL 实现循环：读本体事实 → LLM 从动作注册表选一个动作 → 规则校验引擎核验前置/后置/不变量 → 不满足则拒绝并返回原因给 LLM 重选 → 满足则执行（调用 tool）→ 写回本体真实 → 追加 AuditLog。

#### Scenario: 拒绝后重选（DRV-R-01）
GIVEN LLM 首次选择了前置不满足的动作
WHEN 规则校验拒绝并返回原因
THEN LLM MUST 重新选择满足前置的动作，且业务状态不发生改变

## 确定性能力归属

### Requirement: LLM 只做决策编排（DET-R-01）
时长换算、最低价计算、持久化、邮件网关等确定性能力 MUST 放在 tool/代码中，LLM 只负责动作**选择与编排**，MUST NOT 自行完成此类计算。

## skill / tool 与数字员工

### Requirement: emp-009 与复用规则（SKL-R-01）
- 本体轨 SHALL 由新建 **emp-009** 承接，挂载本体决策层 + skill/tool；emp-008 保持现状并行。
- 现轨 skill/tool SHALL 允许只读复用；任何需要修改的行为 MUST 独立新建，MUST NOT 改动现轨文件。
- 新轨需要的 skill（如 `skill-ont-proc-inquiry`）与 tool（如 `sendMail`/`readInboxThread`/`parseQuote`/`selectApproval`/`storeTrackingNo`）在需修改或不存在时独立创建。

#### Scenario: 复用但零修改（SKL-R-01）
GIVEN 现轨 `tool_send_mail` 可直接满足新轨发信需求
WHEN 新轨复用
THEN 直接只读调用，现轨文件 MUST NOT 被改动

## 并存 / 灰度 / 替换

### Requirement: 灰度守门（GRD-R-01）
- 阶段 A：本体轨只读对照（推断该走哪步，不落库不执行），决策与现轨结果 SHALL 100% 对齐方可进入阶段 B。
- 阶段 B：新任务/新动作放量，规则引擎兜底，可回退。
- 阶段 C：切换入口到本体轨；现轨降为参照/兜底。

#### Scenario: 阶段 A 守门（GRD-R-01）
GIVEN 本体轨处于只读对照
WHEN 某任务的本体轨推断动作与现轨实际结果不一致
THEN 不得放量至该任务，且 MUST 修正/补充规则直至一致

## 幂等与一致性

### Requirement: 幂等（IDS-R-01）
本体轨 SHALL 以 `Email.emailMessageId` 为幂等键；同一邮件重复投递 SHALL 仅入库，不重复执行业务动作。

### Requirement: 审计与溯源（IDS-R-02）
- 每个业务动作执行 SHALL 追加一条 `AuditLog`（仅 insert，MUST NOT update/delete）。
- 通过 taskId SHALL 可溯源到 derivedFrom Session 及全套历史邮件、报价、运单号、工程师最终反馈、审计日志。

## 调度

本规格为行为契约，不绑定具体实现细节；调度驱动本体轨决策循环的方式在实现阶段确定（与现轨 tick 解耦，避免互相干扰）。

## 数据模型

- 本体表（独立 schema）：`O_Session`、`O_Task`、`O_Person`、`O_Email`、`O_SupplierQuote`、`O_AuditLog`（命名以实现为准，但 MUST 独立于 `spare_mail_*`）
- 规则：声明式规则清单（precondition/invariant/rule）

## 追踪

- 设计：`specs/012-ontology-emp009/design.md`
- 代码：`app/`（本体轨新模块，独立）；不修改 `app/routes_procurement_agent.py` 的 mail-inquiry 现轨逻辑
- 测试：`tests/test_ont_emp009_*.py`（新，独立于现轨测试）
- 验收标准：No-011 现轨测试保持全绿（证明零影响）+ 新轨测试全通过