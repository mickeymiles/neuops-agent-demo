# 本体知识层 + LLM 影子验证 留档（NO-012 emp-009）

> 阶段：本体化改造 · LLM 决策回路 + 影子对齐验证
> 日期：2026-08-30 · 状态：主流程与三类异常场景影子验证对齐率 100%

---

## 1. 背景与范式

此前的备件询价实现是"硬编码状态机 + 动作表"，LLM 即便接入也只是套皮。本次改造落地
**本体化（Ontology-driven）智能体**范式，核心变化：

- **不再用状态机指定"某阶段只能做哪个动作"**；
- 而是把领域知识建模为**本体（TBox/ABox）+ 可行动作声明 + 语义规则/不变量**；
- **LLM 基于「当前本体事实(ABox) + 动作定义/条件/不变量」自主分析、决定下一步动作**，并给出理由；
- **语义护栏（validate_action）基于 ABox 事实裁决动作可执行性**：不合法则带原因重问，直到收敛到合法动作。

设计依据来自语义网/知识图谱给 LLM 智能体建模的通行做法：
本体 = **TBox(概念/关系/约束) + ABox(事实)**，可行动作本身是**本体声明（定义+前置+效果+不变量+幂等）**，
规则为 `condition ⇒ 可执行` + `invariant 恒定成立`，校验器在执行前约束并给 LLM 拒绝原因。

---

## 2. 本体知识层结构（`app/ontology/ontology.py`）

| 组成 | 内容 |
|---|---|
| **TBox 概念** | Person / Engineer / Approver / Supplier / Part / InquiryTask / InquiryEmail / Quote / Approval / Order / Shipment / Settlement |
| **TBox 关系** | task.submittedBy(person)、task.invites(supplier)、supplier.offersQuote(task,…)、task.selectedSupplier、task.order(to)、task.shipmentNo、task.closed 等 |
| **可行动作** | 每个动作 = `定义 / 条件(前置) / 效果 / 不变量 / 幂等`，业务语义中文可读 |
| **全局不变量** | ① 同任务对同一语义动作只做一次(B/D/E/G各一次)；② 只前进不回退；③ 发信必落真实线程并携带原文；④ 内部流工程师始终在场、外部流全员回复 |
| **ABox** | `build_abox(task)` 从 `o_task / o_email / o_supplier_quote` 抽取当前事实（含 `inquiry_sent / quote_count / target_supplier_set / order_sent / tracking_number / engineer_feedback_finished / unparseable_supplier_emails` 等） |
| **校验器** | `validate_action(action_id, abox)` 依据动作条件 + 幂等 + 不变量裁决，返回(是否可执行, 原因) |

动作清单（14 个）：
`requestMissingFields / createTask / distributeInquiry / receiveSupplierQuote / finalizeQuoteCollection /
submitApproval / processApprovalDecision / confirmOrderToSupplier / receiveTrackingNumber /
requestTrackingNo / engineerFinalClose / abortTask / requestQuoteClarification / manualCloseTask`

---

## 3. LLM 决策回路 + 影子/信任双模式（`llm.py` / `orbit.py` / `execution.governor`）

- `llm_decide_action(ctx, task)`：把 ABox 事实 + 动作定义/条件/不变量 + 全局不变量序列化为系统提示，
  LLM 提议 `{action, reason}` → `validate_action` 裁决 → 不合法给原因重问(≤N) → 兜底规则建议。
- **影子模式（shadow）**：`ONT_SHADOW=1 / ONT_LLM=0` —— LLM 决策**只记录、不改行为**，执行规则动作，
  每一步落 `align:<动作>` 影子对齐审计（规则 vs LLM vs aligned vs LLM理由），用于积累对齐证据。
- **信任模式（llm）**：`ONT_LLM=1` —— 执行 **LLM 决策**（仍先过 validate_action 语义护栏）。
- `run-full` 经 `asyncio.to_thread` + 进程级串行锁执行，避免 LLM 阻塞调用冻结事件循环、防止调度/手动并发重复发信。

---

## 4. 影子验证结果（服务器真实邮箱，任务级）

### 主流程（PRJ-SRV-04 → OT-验证）
全程对齐 `distributeInquiry → submitApproval → processApprovalDecision → confirmOrderToSupplier →
requestTrackingNo → engineerFinalClose`，终态 `R_SETTLE / R_CLOSED / CLOSED`，G 结算已发。

| 动作 | LLM 理由（摘要） | 与规则 |
|---|---|---|
| distributeInquiry | 任务已立、供应商列表非空、尚未发过询价 → 发B | ✅ |
| submitApproval | 报价收集结束 → 发起审批汇总D | ✅ |
| processApprovalDecision | 已发D且收到审批回复 → 校验所选是否在有效候选池 | ✅ |
| confirmOrderToSupplier | 已收有效报价+审批已定供应商+尚未下订 → 发订货E | ✅ |
| requestTrackingNo | 回执无单号 → 主动索取 | ✅ |
| engineerFinalClose | 已登记运单号且工程师反馈完成 → 发G闭环 | ✅ |

### 异常场景（影子对齐率 100%）

| 场景 | 触发 | LLM 决策 | 与规则 | LLM 理由 |
|---|---|---|---|---|
| A 缺字段 | 工程师询价缺 `pn/count/address` | `requestMissingFields` | ✅ | 必填为空，应先回信要求补齐，不建任务不询价 |
| B 到期中止 | 到截止且无任何有效报价 | `abortTask` | ✅ | 已到截止且无有效报价 → 发中止通知F关闭 |
| C 报价解析失败 | 供应商回线程但解析不出报价 | `requestQuoteClarification` | ✅ | 收到无法解析报价 → 回信请补单价/货期后重发，保持收集不中止 |

> 场景 C 起初是语义缺口：系统（及 LLM）把"有回复但解析失败"误当成"无回复→干等"。
> 通过新增**事实** `unparseable_supplier_emails` 与**动作** `requestQuoteClarification`（+语义规则）补齐，
> 区分了「无回复→到期中止」与「有回复但失败→催补重发」。复验后 LLM 正确选择并实际给供应商回信。

---

## 5. 结论与后续

- 本体知识层已落地，LLM 决策在语义护栏内与规则天然一致（对齐率 100%），且理由可读、可审计、可追溯。
- **信任模式切换前提**：继续让影子多跑不同场景，确认对齐率稳定为 100%（或仅出现"LLM 合法但更优"的可接受分岐）后，再把 `governor.llm` 置 1 让 LLM 直接执行。
- 治理：任意时刻可用 `POST /api/ontology-emp009/governor` 切换 `mode/roll/exec_enabled/llm`；回退只需 `llm=false` 回到规则驱动。
- 相关代码：`app/ontology/{ontology,llm,orbit,decision,execution,engine,routes}.py`

### 文档索引
- 本轨设计：`specs/012-ontology-emp009/design.md`
- 本轨需求：`specs/012-ontology-emp009/spec.md`
- 本文档：`specs/012-ontology-emp009/shadow-validation-report.md`