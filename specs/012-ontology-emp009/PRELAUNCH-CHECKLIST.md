# 采购智能体（emp-009 本体轨）上线试运行准备清单

> Date: 2026-09-01
> Component: emp-009 备件询价智能体（本体轨）+ 9006 可观测页面
> 服务器：`ubuntu@122.51.98.98`（`neuops-9007` 本体轨 / `neuops-9006` 页面）
> 配套：`IMPLEMENTATION.md`（§7 复跑手册、§9 三要素接线度、§10 地基四类薄弱点）

---

## 0. 一句话结论

功能链路 **A→F 已用真实 163 邮箱端到端跑通**，本地本体测试 **64 例全绿**，emp-009 邮箱凭据与启用状态均正常。
但**线上代码落后于本地未提交改动**，且因线上仍是旧版、**G 结算闭环当前实际仍在发**（与"暂不需要结算、预留开关"的业务决定相反）。

> **上线试运行前必须先完成 P0 四项**：提交本地改动 → 部署两服务 → 清场（库 + 邮箱）→ 确认决策模式。

---

## 1. 现状盘点

### 1.1 代码与提交状态（本地）

| 仓库 | 分支/Commit | 未提交改动 |
|---|---|---|
| `neuops-agent-demo` (9007) | `main` @ `b3dd375` | **改**：`app/config.py`、`app/ontology/{decision,execution,orbit}.py`、`specs/.../design.md`、`tests/ont_cotest_local_driver.py`、`tests/test_ont_cc_propagation.py`、`tests/test_ont_emp009_flow.py`<br>**新增**：`ont_topo_build.js`、`ontology_foundation_preview.html`、`specs/012-ontology-emp009/IMPLEMENTATION.md` |
| `contract-compare-9006` (9006) | `main` @ `dd8b431` | **改**：`frontend/procurement.html`、`frontend/procurement.app.js`（新增「🕸 拓扑与一致性」面板） |

改动意图已逐条核对，均为有意改动、无遗留垃圾：
- 源码 4 处 = **结算开关 `ONT_SETTLEMENT_ENABLED` 门控**（默认 `0` 关闭 G）。
- `ont_cotest_local_driver.py` = 按需求**去掉观察者 `biqzh@neusoft.com`**（`EXPECT_CC` 仅剩 b5 + 260110550@qq.com）。
- 两个测试文件 = 顶部显式 `ONT_SETTLEMENT_ENABLED=1`，**保留 G 抄送透传的回归护栏**（运行时默认关）。
- ✅ 已排查：源码与测试中 `fengzhengyi` / `lihua@` / `li.rg@` / `TEMP_CC_ONCE` **零命中**，无残留观察者。

### 1.2 线上实况（122.51.98.98）

| 项 | 状态 |
|---|---|
| `neuops-9007.service` | **active**（本体轨+现轨） |
| `neuops-9006.service` | **active**（Contract Compare） |
| 线上代码时间 | Aug 31 15:02 |
| 是否已含结算开关 | ❌ **否** — `grep -c settlement_enabled app/config.py` = **0**（旧版） |
| 本体库残留 | ⚠️ `o_task=1`、`o_email=1`、`o_supplier_quote=0` |
| emp-009 启用 | ✅ `employees.enabled=1` |
| emp-009 邮箱渠道 | ✅ `employee_channels(emp-009, email).enabled=1`，config 非空且含口令字段 |
| emp-008 现轨 | ⚠️ `enabled=1` 但**无 email 渠道**，且线上 `PROC_MAIL_USERNAME` 为空 → **现轨不干活** |

> emp-009 邮箱凭据已持久化在服务器 `neuops_sessions.db`（此前"009 用空口令不认领 A"的根因已消除）。
> 试运行**只跑本体轨 emp-009** 即可，现轨不影响。

### 1.3 配置确认表

| 开关 | 线上值 | 本地值 | 判定 |
|---|---|---|---|
| `ONT_MODE` | `ontology` | `ontology` | ✅ 本体轨 |
| `ONT_EXEC` | `1` | `1` | ✅ 真实发信/落库 |
| `ONT_SCHEDULER` | `1` | `1` | ✅ 自动调度开 |
| `ONT_SCHEDULER_USE_LLM` | **未设 → 默认 `0`（纯规则）** | `1` | ⚠️ **不一致**，见 §3 决策点 |
| `ONT_LLM` / `ONT_SHADOW` | 未设 | `1` / `1` | 线上未开影子 |
| `ONT_SETTLEMENT_ENABLED` | 未设（且旧代码无此开关，**不生效**） | 未设 → `0` | ⚠️ **部署新版后才生效** |
| `ONT_MAIL_USERNAME` | `biquanzhi4@163.com` | 同 | ✅ b4 采购智能体 |
| `ONT_SUPPLIERS` | 中软国际:biquanzhi2 / 神州数码:biquanzhi6 | 同 | ✅ |
| `ONT_APPROVERS` | `biquanzhi5@163.com` | 同 | ✅ 李审批 |
| `ONT_REQUESTERS` | `biquanzhi1@163.com` | 同 | ✅ 张运维（发起人白名单） |
| `ONT_SCAN_HOURS` | `48` | `48` | ✅ |
| `ONT_DB_PATH` | `/home/ubuntu/neuops-agent-demo/neuops_ontology.db` | 本机 mac 路径 | ✅ 线上正确 |
| `PROC_MAIL_USERNAME` | **空** | `biquanzhi3` | ⚠️ 现轨线上无邮箱 |

> `.env` 被 rsync 排除、各环境独立，**本地路径不会污染线上**；但反过来，**改开关必须改服务器上的 `.env`**。

---

## 2. P0 阻塞项（上线前必须做完）

1. **部署新版（最关键）** — 线上旧代码无 `settlement_enabled`，工程师发"更换完成"会**真的发出 G 结算邮件**，与"暂不需要结算"冲突。部署新版后默认关闭。
2. **提交并推送两仓库本地改动**（当前全部未提交、未推送）。
3. **清场** — 停 009 → 清本体库八张表 → 清 6 个 163 邮箱 → 起 009。当前库内有 1 个残留任务/邮件，不清会混进试运行数据、难以判读结果。
4. **确认决策模式**（规则 vs LLM）— 见 §3。

---

## 3. 决策点（需拍板）

**决策模式。** 线上 `ONT_SCHEDULER_USE_LLM` 未设 → 默认 `0` → **纯规则硬状态机**（`decision.py` S1–S5），这条路径已用真实邮箱验证跑通 A→F，最稳。本地 `.env` 设了 `1`（LLM 决策 + 影子）。

- **推荐：试运行先用规则模式**（即线上现状，不改），最稳且已验证。
- 待稳定后若要"真本体化"，再设 `ONT_SCHEDULER_USE_LLM=1`——注意按 §9 审计，**只有开了 LLM，本体声明才真正参与决策**；同时建议开 `ONT_SHADOW=1` 影子对比，避免决策漂移。

**本体地基四类薄弱点是否阻塞上线？不阻塞。**
① 6 个孤立概念 ② 孤儿声明 `requestQuoteClarification` ③ 状态词表漂移（`R_ORDER` vs `ORDER_CONFIRM`）④ 声明↔执行漂移（11 条规则仅 `createTask` 被消费）—— 都属于"纸面本体"层面的架构债，**A→F 靠硬逻辑跑通不受影响**。已在 `IMPLEMENTATION.md` §10 记录，后续按 §10.4 四步收敛。

---

## 4. 上线步骤（按序执行）

### 4.1 提交与推送（两仓库）
```bash
# 9007
cd /Users/macbook/AI-Agent/neuops-agent-demo
git add -A && git commit -m "feat(ont): 结算闭环 G 默认关闭(预留开关) + 本体地基拓扑面板 + 实现现状文档"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git push origin main

# 9006
cd /Users/macbook/AI-Agent/contract-compare-9006
git add -A && git commit -m "feat(ont): 本体可观测新增「拓扑与一致性」面板"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git push origin main
```
> 必须 `env -u *PROXY*` 走 SSH，否则 GitHub 443 超时（HTTPS 走本机代理会 502）。

### 4.2 部署 9007
```bash
rsync -avz --exclude .git --exclude .venv --exclude __pycache__ --exclude .env \
  --exclude 'backup_deploy_*' -e "ssh -i ~/.ssh/neuops_ci_deploy" \
  ./ ubuntu@122.51.98.98:/home/ubuntu/neuops-agent-demo/

ssh -i ~/.ssh/neuops_ci_deploy ubuntu@122.51.98.98 \
  'sudo systemctl restart neuops-9007 && sleep 3 && systemctl is-active neuops-9007'
```

### 4.3 部署 9006（拓扑面板）
同步到 9006 部署目录后，在**服务器部署目录内**执行：
```bash
bash scripts/remote_deploy.sh   # 自建 venv → 装依赖 → 装 systemd → 重启 → 健康检查
```

### 4.4 验证新版已生效（关键）
```bash
ssh -i ~/.ssh/neuops_ci_deploy ubuntu@122.51.98.98 \
  'cd /home/ubuntu/neuops-agent-demo && grep -c settlement_enabled app/config.py'
```
**期望 ≥1（当前为 0）**，为 0 说明没部署上，G 仍会发。

### 4.5 清场（务必先停服务，否则 009 会重认领残留邮件）
按 `IMPLEMENTATION.md` §7 一键复跑手册：
1. `sudo systemctl stop neuops-9007`
2. 清 6 个 163 邮箱（**直连 `imap.163.com:993`**，代理隧道已废弃），等 163 异步 expunge
3. 清本体库八张表：`o_task / o_email / o_supplier_quote / o_audit_log / o_alignment / o_session / o_scan_state / o_person`
4. `sudo systemctl start neuops-9007`

### 4.6 试运行冒烟
- 张运维(b1) 向 b4 发一封**字段齐全**的询价 A。
- 观察链路：b2/b6 收到 B → 报价 → b4 生成 D 汇总（给 b1、抄送 b5）→ b5 确认 → b4 发 E 给中标供应商 → 供应商回快递单号 → **停在此**。
- **验收点**：① E 主送**仅**中标供应商、其余（b1/b5/观察者）一律抄送；② 工程师发"更换完成"后**任务直接 CLOSED、不再发 G**。

---

## 5. 风险与降级

| 风险 | 影响 | 降级 / 应对 |
|---|---|---|
| **G 结算误发**（未部署新版时） | 供应商收到不该有的结算邮件 | 部署新版即默认关闭；新版下应急设 `ONT_SETTLEMENT_ENABLED=0` 重启 |
| 009 邮箱凭据失效 | 不认领 A，流程不启动 | 检查 `employee_channels(emp-009,email)`；回退 `ONT_MAIL_PASSWORD` |
| 残留数据混入 | 试运行结果难以判读 | 上线前清库 + 清邮箱（§4.5） |
| LLM 决策漂移（若开 `USE_LLM`） | 选错动作/供应商 | 试运行先不开；开则配 `ONT_SHADOW=1` 影子对比 |
| 发起人白名单漏配 | 非白名单询价不被认领 | 确认 `ONT_REQUESTERS=biquanzhi1@163.com` |
| 现轨 emp-008 不工作 | 仅现轨，本体轨不受影响 | 试运行只跑本体轨 |
| 163 邮箱清理慢 | 清场不彻底 | 清后 `sleep 20` 等异步 expunge；**清理前必须停 009** |

---

## 6. 回滚

- **代码回滚**：服务器非 git 仓库，部署前先在服务器 `cp -a app app.bak-$(date +%s)` 备份，需要时 rsync 回退。
- **服务回滚**：`sudo systemctl restart neuops-9007`（9006 同理）。
- **数据回滚**：按 §4.5 清库。
- **紧急停摆**：`ONT_SCHEDULER=0`（总闸，页面启用也不起）或页面关闭 emp-009 开关（`runtime.sync_scheduler` 会真实取消监听线程）。

---

## 7. 追踪

- `IMPLEMENTATION.md` §7 一键复跑手册 / §9 本体三要素真实运转度 / §10 本体地基增强与四类薄弱点
- `design.md`（V0.2 目标范式，已标注"已实现并验证"并指向 IMPLEMENTATION.md）
