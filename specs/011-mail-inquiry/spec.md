# NO-011 备件邮件询价数字员工 — 设计规格

> Document Version: V1.0
> Date: 2026-08-28
> Component: emp-mail-inquiry + skill-proc-mail-inquiry
> Status: 生效（作为测试用例单一事实源）

## Purpose

面向现场工程师**仅通过邮件**发起的备件询价采购，实现全流程邮件自动化：
工程师邮件发起询价 → 系统自动生成任务号 → 向供应商发询价邮件 → 收集报价 → 计算最低价 →
汇总邮件抄送审批人 → 审批人确认 → 下达订货邮件 → 闭环。

区别于既有 emp-008（平台驱动、项目经理操作），本员工为**邮件驱动**，全程无需工程师/供应商登录平台。

## 角色与邮箱约定

| 角色 | 交互 | 说明 |
|------|------|------|
| 工程师 | 发送询价申请（模板 A）到采购邮箱 | 无平台入口 |
| 系统（emp-mail-inquiry） | 收 A → 发 B 询价 / D 汇总 / E 订货 / 异常回信 | 自动 |
| 供应商 | 回复 C 报价；接收 B 询价、E 订货 | 邮件 |
| 审批人 | 回复 D 汇总（确认 / 指定供应商 / 全部拒绝） | 白名单邮箱 |

采购邮箱 = `proc_mail_username`（发件与收件同一邮箱）。

## 状态机

```
PARSING → SENDING_B → WAITING_QUOTES → DECIDING_LOWEST → WAITING_APPROVAL → ORDERING → DONE
   │(格式异常→回信阻断，不建任务)
   └→ REJECTED(格式异常标记)
无有效报价 → 由 DECIDING_LOWEST 发模板 F 中止 → DONE(ABORT_NO_QUOTE)
审批人全部拒绝 → 发模板 F 中止 → DONE(ABORT_ALL_REJECTED)
```

## 邮件模板

| 模板 | 用途 | 触发方→收件 |
|------|------|------|
| A | 工程师发起询价 | 工程师→采购邮箱 |
| B | 对外询价（**不含收货地址**） | 系统→供应商 |
| C | 供应商回复报价 | 供应商→采购邮箱 |
| D | 内部汇总·最低价优选·**抄送审批人** | 系统→工程师会话 + 抄送审批人 |
| E | 下达订货（**含收货地址**、联系人、要求测试报告/快递单号） | 系统→选中供应商 |
| F | 中止通知 | 系统→工程师（回复 A/D 会话） |

模板正文与主题由 `spare_mail_config` 数据库配置维护（DB 优先，skill JSON 兜底）。

---

## Requirement: R-FR-01 识别工程师询价邮件并建任务

系统 SHALL 识别收件箱中主题含「询价」关键字且非回复（无 In-Reply-To/References、主题不以 Re:/回复 开头）的邮件，作为工程师询价申请。

### Scenario: 识别有效询价
GIVEN 采购邮箱收到来自工程师、主题含「询价」、非回复字段的新邮件
WHEN 执行 tick（PARSING）
THEN 系统判定为询价申请并进入字段抽取；命中后创建任务（状态 SENDING_B）

### Scenario: 忽略非询价邮件
GIVEN 采购邮箱收到主题不含「询价」关键字的普通邮件
WHEN 执行 tick（PARSING）
THEN 系统忽略该邮件，不建任务、不回信

### Scenario: 忽略采购方自身的转发/恢复
GIVEN 超出 `since_minutes` 窗口、或来自采购方自身邮箱的邮件
WHEN 执行 tick（PARSING）
THEN 系统忽略

## Requirement: R-FR-02 必填字段校验与格式异常回信（阻断）

系统 MUST 从询价邮件抽取项目编号、项目名称、备件类型、品牌、PN、规格、成色、数量、收货地址、询价时限、最晚发货时间等字段。凡**关键必填字段缺失或整体无法解析**，系统 SHALL 向工程师**自动回复邮件指出缺失字段/格式问题**，且**不得进入询价流程**（不建任务、不发 B 询价）。

必填字段（关键）：`part_type`、`brand`、`pn`、`count`、`spec`。

### Scenario: 缺关键字段 → 回信指出且不推进
GIVEN 工程师询价邮件正文缺少必填字段（如无品牌/无 PN/无数量）
WHEN 执行 tick（PARSING）完成字段校验
THEN 系统向工程师回复邮件，明确列出缺失字段；且不创建任务、不发 B 询价邮件，任务不进入流程

### Scenario: 完全无法解析 → 回信提示格式
GIVEN 邮件看似询价（主题含「询价」）但正文无法解析出任何字段
WHEN 执行 tick（PARSING）
THEN 系统回复工程师说明格式不规范/无法识别，且不推进流程

### Scenario: 正常邮件不误报
GIVEN 字段齐全的询价邮件
WHEN 执行 tick
THEN 不回复异常提示，正常建任务

## Requirement: R-FR-03 重复邮件判重

系统 MUST 避免同一询价邮件被重复建任务。判重依据为邮件 `thread_msg_id`（RFC Message-ID）。

### Scenario: 重复邮件不重复建任务
GIVEN 同一询价邮件再次出现（如重拉/重发同 Message-ID）
WHEN 执行 tick
THEN 已存在的 thread_msg_id 跳过，不重复建任务、不重复回信

## Requirement: R-FR-04 对外询价 B（屏蔽收货地址）

系统 SHALL 在 SENDING_B 向配置供应商池的每家供应商发送 B 询价邮件，正文**不得包含工程师收货地址**，并在文中提示"收货信息将在确定供应商后于订货邮件中单独告知"。

### Scenario: B 邮件不含地址
GIVEN 已建任务且供应商已配置
WHEN 执行 tick（SENDING_B）
THEN 每家供应商收到 B 邮件，正文不含收货地址；任务转 WAITING_QUOTES

### Scenario: 供应商池为空
GIVEN 未配置任何供应商
WHEN 执行 tick（SENDING_B）
THEN 任务不发送 B 询价，记录 no_sent_suppliers 并进入后续逻辑（不崩溃）

## Requirement: R-FR-05 报价收集 C 与非标处理

系统 SHALL 在 WAITING_QUOTES 读取收件箱，用 `In-Reply-To`/`References` 精确匹配 B 的 Message-ID，仅接受**供应商白名单**发件人的回复作为报价。报价解析 MUST 支持多种格式：纯文本字段、Markdown 表格、复杂排版（嵌套引用）；无法解析的报价 SHALL 记录可读原文，不得静默丢弃导致误判为无报价。

### Scenario: 纯文本报价
GIVEN 供应商回复含「单价：1000」「成色：全新」「数量：2」「货期：3天」
WHEN 执行 tick（WAITING_QUOTES）
THEN 报价中正确解析出单价/成色/数量/货期

### Scenario: 表格报价
GIVEN 供应商回复为 Markdown 表格（表头含 数量/单价/货期/成色 列）
WHEN 执行 tick
THEN 按表头定位列并解析出单价/数量/货期/成色

### Scenario: 非供应商发件人被忽略
GIVEN 收件箱有匹配线程但发件人不在供应商白名单
WHEN 执行 tick
THEN 该邮件不作为报价，忽略

### Scenario: 报价无法解析时保留原文
GIVEN 供应商已回复但正文无单价数字等可解析信息
WHEN 执行 tick
THEN 该报价记录保留 raw_body 原文并标记可解析性，可进入人工/后续判断，不当作"无报价"静默丢弃

## Requirement: R-FR-06 推进条件与最低价优选

系统 SHALL 在满足「全部已回复的供应商」或「报价截止时间到达」时，由 WAITING_QUOTES 转 DECIDING_LOWEST，按单价排序取**最低价为唯一优选项**，展示全部有效报价。

### Scenario: 收齐报价 → 最低价优选
GIVEN 两家供应商均已报价（¥1000、¥1280）
WHEN 满足推进条件转 DECIDING_LOWEST
THEN lowest_supplier = ¥1000 供应商，lowest_quote 记录该报价，任务转 WAITING_APPROVAL

### Scenario: 无有效报价 → F 中止
GIVEN 到点但所有报价迟到或单价不可解析
WHEN 执行 tick（DECIDING_LOWEST）
THEN 发送模板 F 中止通知，任务 DONE(ABORT_NO_QUOTE)

## Requirement: R-FR-07 内部审批 D 与审批人确认

系统 SHALL 在 DECIDING_LOWEST 向工程师会话回复模板 D 汇总邮件，**抄送审批人**，列全部报价并系统提示最低价优选。审批人回复 D 邮件进行二选一：确认最低价 / 指定其他供应商；亦支持全部拒绝终止。**仅白名单审批人**的回复被采纳。

### Scenario: 审批人确认最低价
GIVEN 审批人回复含「确认采购」
WHEN 执行 tick（WAITING_APPROVAL）
THEN target_supplier = lowest_supplier，转 ORDERING

### Scenario: 审批人指定其他供应商
GIVEN 审批人回复含「确认采购 …供应商2…」（指定非最低价供应商）
WHEN 执行 tick（WAITING_APPROVAL）
THEN target_supplier = 指定的供应商而非最低价，转 ORDERING

### Scenario: 审批人全部拒绝
GIVEN 审批人回复含「全部报价不可选/终止询价」
WHEN 执行 tick
THEN 发送模板 F 中止，任务 DONE(ABORT_ALL_REJECTED)

### Scenario: 非审批人回复被忽略
GIVEN 收件箱有匹配 D 线程但发件人非审批人白名单
WHEN 执行 tick
THEN 忽略该回复，继续等审批人

### Scenario: 未配置审批人
GIVEN approver_emails 为空
WHEN 执行 tick
THEN 自动采纳最低价 target=lowest_supplier，approval_state=auto_approved，转 ORDERING

### Scenario: 审批人未回复
GIVEN 无审批人回复命中
WHEN 执行 tick
THEN 任务保持 WAITING_APPROVAL

## Requirement: R-FR-08 下达订货 E

系统 SHALL 在 ORDERING 向 target 供应商发送模板 E 订货邮件，**回复该供应商报价会话**，包含收货地址、收货联系人、联系电话、最晚发货时间、要求测试报告与快递单号。

### Scenario: 正常订货闭环
GIVEN target_supplier 已确定且其报价邮件含 Message-ID
WHEN 执行 tick（ORDERING）
THEN 向该供应商发送 E 邮件（reply_to 报价会话，含收货地址），任务 DONE(ORDER_CONFIRMED)

## Requirement: R-FR-09 配置维护

静态配置（审批人、供应商池、邮件模板、凭据）SHALL 存于 `spare_mail_config`（DB），优先于 skill JSON 与 .env。`mail_configured` 依据 DB 凭据判定。

### Scenario: 配置 DB 优先
GIVEN DB 中已配置审批人/供应商/模板
WHEN 流程读取配置
THEN 使用 DB 值而非 skill/.env 默认值

### Scenario: 配置未落库用默认
GIVEN DB 配置为空
WHEN 首次访问配置 API
THEN 自动从 skill JSON 下沉默认参与方与模板到 DB（幂等）

## Requirement: NFR-R-01 幂等与单点异常隔离

每个 tick 内各 step 独立 try/except，单个任务异常 SHALL 不影响其它任务推进；DB 建表/写配置幂等。

### Scenario: 单任务异常不阻塞其它
GIVEN 某任务在某 step 抛异常
WHEN 执行 tick
THEN tick 记录该任务 error 至 latest_step，继续处理其它任务

## Requirement: NFR-R-02 凭据安全

密码类字段（邮箱授权码、飞书 secret、BITABLE token）在配置读取 API 中 MUST 打码展示；SMTP/IMAP 登录使用 DB 凭据，缺失时降级 .env 并允许 emp-008 兼容。

### Scenario: 密码打码
GIVEN 读取配置 API（mask=true）
THEN 密码字段显示为 `xx****` 而非明文

---

## 数据模型

- 动态状态：`spare_mail_task`（task_id/thread_msg_id/status/latest_step/suppliers_json/quotes_json/lowest_* /approval_*/target_supplier/...）
- 静态配置：`spare_mail_config`（config_key → json）

## 追踪

本规格对应代码：`app/routes_procurement_agent.py`（mail-inquiry 段）、`app/db/spare_mail.py`、`app/mcp_tools.py`、`app/db/schema.py`。
测试映射见 `tests/`。