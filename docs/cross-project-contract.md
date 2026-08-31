# 跨工程契约：contract-compare-9006 ⇄ neuops-agent-demo

> 目的：把两个工程之间「没人写下来、但双方都在依赖」的约定显式化。
> **这份文档是重构的输入**——契约没固化之前动手重构，等于摸黑拆炸弹。
>
> 现状：9006 = 业务主数据 + 页面（端口 9006）；9007 = 智能体执行（端口 9007，邮件/飞书/状态机）。
> 9006 **不含** smtplib / imaplib / 飞书 SDK，邮件收发与通知 100% 委托 9007。

---

## 一、三条协作通道

| # | 通道 | 方向 | 机制 |
|---|---|---|---|
| 1 | HTTP trigger | 9006 → 9007 | `POST {NEUOPS_BASE}/api/procurement-agent/{path}`，失败不阻断主流程 |
| 2 | 共享 SQLite | 9007 → 9006 库文件 | 直连 `contract_compare.db` 读写，**不走 API** |
| 3 | 飞书卡片回调 | 9007 → 9006 → 9007 | 卡片按钮 → `/card-callback` → `:9006/.../select` → 再 trigger 回 9007 |

### 通道 1：4 个 trigger

`NEUOPS_BASE` 默认 `http://127.0.0.1:9007`，超时 `NEUOPS_TRIGGER_TIMEOUT`（默认 45 秒，原为硬编码 15 秒）。

| path | 触发时机 | payload | 9007 行为 |
|---|---|---|---|
| `trigger/task-created` | 建任务（页面 / Agent 入口） | 整个 task 对象 | flow-01 落库确认 + flow-02 组发询价邮件 + 飞书 `task_created` |
| `trigger/task-selected` | 选型确认 | `{task, selected_supplier, deal_unit_price, source}` | flow-05 发采购确认邮件 + 飞书 `confirm_purchase` |
| `trigger/test-result` | 录入测试结果 | `{task, test_result, remark, source}` | flow-07/08：通过→写台账+闭环+验收邮件；失败→`test_failed` 告警 |
| `trigger/task-canceled` | 取消任务 | `{task, cancel_reason, source}` | flow-09，仅飞书通知，不写库 |

**`source` 是隐藏控制位**：
- `page` / `agent` / `email` → 三入口标识，落 9006 `procurement_task.source`
- `card_callback` → 表示来源是飞书卡片按钮，9007 会 `skip_feishu_notify=True`，**避免弹出第二张卡片**
  （见 `_flow_proc_05_confirm_selection` 的 `skip_feishu_notify` 参数）

### 通道 2：共享数据库

`PROC_9006_DB_PATH`（`app/config.py`）。**必须显式设置**：

```bash
PROC_9006_DB_PATH=/absolute/path/to/contract-compare-9006/contract_compare.db
```

> 坑：代码默认值拼的是 `<上级目录>/contract-compare/contract_compare.db`（按服务器目录名），
> 本机仓库名是 `contract-compare-9006`，默认路径必然不存在，不显式指定会静默连到错误的库。
> `app/db/contract_mail.py` 有同样默认值。

9007 可直读写的表（`_PROC_TABLE_MAP`）：

| 表 | 9007 权限 |
|---|---|
| `procurement_task` | 读写（upsert 状态与报价） |
| `procurement_ledger` | 写（闭环台账） |
| `procurement_master_data` | 读 |
| `procurement_op_log` | 写 |
| `procurement_supplier` | 读 |
| `procurement_contract` | 读（取 PM 邮箱 / 收件信息） |
| `procurement_contract_supplier` | 读 |
| `procurement_mail_cc` | 读（全局抄送） |
| `procurement_spare_part` | 读（备件主数据反查） |

补列机制：`procurement_models._ensure_columns` 幂等 ALTER，`contract_mail._ensure_columns` 亦然。
**字段只能增不能改**，这是共享 DB 直连带来的最大约束。

### 通道 3：飞书回调闭环

```
PM 点卡片按钮
  → 9007 POST /api/procurement-agent/card-callback
  → 9007 POST :9006/api/procurement/tasks/{id}/select  (source=card_callback)
  → 9006 落库后 trigger_neuops("trigger/task-selected", source=card_callback)
  → 9007 flow-05 发确认邮件，但 skip_feishu_notify=True（不再弹新卡片）
```

---

## 二、状态机：目前有两份推导（重构重点）

| 位置 | 文件 | 作用 |
|---|---|---|
| 9006 前端 | `frontend/procurement.app.js` `renderUnifiedFlow()` | 按 `external_status` 排名渲染 9 节点 |
| 9007 | `app/db/contract_mail.py` `_derive_task_status()` | 由双流推导 `task_status` 回写 9006 |

**两份逻辑独立实现，是人肉同步的。改任一侧都必须同步另一侧。**

双流取值：

- `internal_status`：`R_INIT` → `R_APPROVAL` → `R_CLOSED`
- `external_status`：`R_SEND` → `R_WAIT_QUOTES` → `R_DECIDING` → `R_ORDER` → `R_WAIT_SHIPPING` → `R_WAIT_ACCEPTANCE` → `R_WAIT_SETTLE` → `R_CLOSED`，异常 `R_ABORT`

9 节点映射：发起询价 → 发询价函 → 供应商报价 → 比价定标 → 内部审批 → 下达订货 → 发货回执 → 收货验收 → 结算通知。
异常（`R_ABORT` 或「任务已取消」）时前端追加第 10 张「已终止」卡。

---

## 三、邮件模板与解析契约

详见 `docs/inquiry-email-template.md`（第一封申请邮件的标准）。

| 模板 | 用途 | 标题格式 |
|---|---|---|
| A | 工程师发起询价 | `【备件询价】{project_no} {project_name} — {brand} {pn} x {count}` |
| B | 对外询价（供应商） | `【询价】{brand} {pn} x {count} — {urgent} 内回复 [{task_no}]` |
| C | 供应商回复归档 | — |
| D | 内部汇总（审批人） | `【询价汇总】{project_no} {brand} {pn} — {n}家报价-最低价优选 [{task_no}]` |
| E | 下达订货 | `【订货确认】{project_no} {brand} {pn} x {count} — 请安排发货 [{task_no}]` |
| F | 任务中止 | — |
| G | 结算 | — |

**关键词契约**（回复必须命中，否则流程不推进）：

| 环节 | 发件人 | 必须包含的关键词 |
|---|---|---|
| 审批批准 | 审批人白名单 | `确认采购` / `同意采购` / `批准采购` / `确认订货` / `批准订货` / `采购通过` |
| 审批拒绝 | 审批人白名单 | `全部报价不可选` / `全部不可选` / `任务终止` / `终止询价` / `全部拒绝` |
| 验收回执 | 工程师（非审批人） | `备件更换完成` / `更换完成` / `到货更换完成` |

> 这是隐式契约里最脆弱的一环：审批人写了「同意」二字但没连着「采购」，流程会静默挂起。
> 重构时应改为语义判断或结构化回执，别再依赖精确词组。

**线程契约**：任何一步回复都必须保留 `In-Reply-To` / `References`，
否则 9007 匹配不到任务（表现为 tick 报 `processed: 0`）。

---

## 四、已知不一致清单（重构待办）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| 1 | 状态推导两份实现 | 9006 前端 JS vs 9007 `_derive_task_status` | 改一侧忘另一侧 → 状态错乱 |
| 2 | 共享 DB 直连 | 9007 直写 9006 表 | 字段只能增不能改，无接口契约 |
| 3 | `update_task_quote` / `update_task_letter` 死代码 | 9006 `procurement_models` | 9007 零调用，误导维护者 |
| 4 | trigger 同步阻塞 | 9006 `trigger_neuops` | 耗时随 9007 流程波动（已把 15s 放宽到 45s，长期应异步化） |
| 5 | 审批关键词过于精确 | 9007 `_mi_internal_wait_approval` | 措辞不符就静默挂起 |
| 6 | 模板变量命名两套 | `part_brand`(ctx) vs `{brand}`(模板) | 已用 `_build_inquiry_tpl_ctx` 桥接，长期应统一 |
| 7 | 测试与实现脱节 | `tests/test_mail_inquiry_e2e.py:148` 断言审批人为 `biqzh@neusoft.com`（实际 `biquanzhi5@163.com`）；<br>`tests/test_mail_inquiry_abnormal.py` 仍断言「缺字段不建任务」（现在会建 REJECTED 记录） | 基线即红，无法当回归护栏 |
| 8 | `procurement_supplier` 数据角色混乱 | 9006 | 曾把智能体邮箱 b3 配成供应商，导致智能体给自己发信 |
| 9 | `procurement_contract.pm_email` 角色混乱 | 9006 | 有 PM 邮箱用了供应商邮箱 |
| 10 | 9006 测试零覆盖采购链路 | 9006 `tests/` | 出现过「161 个测试全绿但主流程因缺列不可用」 |

---

## 五、已修（2026-08-30）

- `bootstrap.sh` 补 `init_procurement_db()` + 采购域 schema 校验
- 新增 `tests/test_procurement_schema.py`（3 条 schema 守卫）
- `.env.example` 补 `PROC_9006_DB_PATH` / `PROC_9006_BASE` 及默认值缺陷说明
- 模板 A 修正三处（成色 / 项目编号与名称拆分 / 补收货地址），已同步运行时
- trigger 超时 15s → `NEUOPS_TRIGGER_TIMEOUT`（默认 45s）
- 9006 `NewTaskBody` 补齐备件属性字段 + 路由透传
- 9007 flow-02 改为**模板优先**（变量齐全用模板 B，不足才回退 LLM），
  新增 `_build_inquiry_tpl_ctx` / `_tpl_ready` / `_send_inquiry_by_template`
- `TaskInstance` 补齐备件属性与双流字段
- 产出 `docs/inquiry-email-template.md`
