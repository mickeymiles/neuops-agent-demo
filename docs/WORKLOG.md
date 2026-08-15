# NeuOps 工作记录（WORKLOG）

> 本文件按时间线整理 NeuOps 一体化运维监控平台 Demo 的搭建、修复与验证过程。
> 详细功能说明见 [README.md](../README.md)。

---

## 一、代码架构重构（初始阶段）

**目标**：将单文件 `main.py` 拆分为按领域组织的 `app/` 包，保持行为 100% 兼容。

| 内容 | 说明 |
|---|---|
| 业务领域拆分 | `agent_chat` / `routes_*` / `db` / `config` / `knowledge` / `mcp_tools` / `devtools` / `feishu_notify` 等 |
| 数据与代码分离 | `seed_data.py` 抽离种子数据（技能/员工/会话/MCP 映射），启动时导入 |
| 薄入口 | `main.py` 只负责组装 app、挂载路由、初始化 DB、启动探针与引擎 |
| 拆分工具 | `scripts/split_refactor.py` |

**成果**：34 项 pytest 全绿，本地端到端验证通过。

---

## 二、NeuOps 一体化运维监控平台主功能

**对应提交**：`1af71b3 feat: NeuOps 一体化运维监控平台 - 本体拓扑/真实采集/全自动自愈/DevOps 闭环`

### 1. 统一监控探针（app/probe/）
- 六类真实采集：服务器 / 容器 / 数据库 / 网络 / 中间件 / 应用（psutil + 真实命令 + 端口/进程识别）
- 应用日志增量采集（`log_collector`，tail 方式，可配置路径）
- 后台线程周期调度（30s），支持手动采集、CLI、远程 HTTP 上报（ingest）

### 2. 运维本体拓扑（ops_ontology）
- 五类实体 + 三类关系，`/api/ops/topology` 接口
- /ops 页面拓扑可视化

### 3. 全自动自愈引擎（ops_self_heal）
- incident 状态机：`detected → repairing → verifying → recovered`，失败升级
- 白名单动作：`restart_9006` / `restart_9007` / `restart_self` / `code_heal`
- 安全护栏：开关 / 最大重试 / 健康验证 / 失败飞书
- 事件全量审计（fix_action / fix_log / 时间线）

### 4. 告警引擎（alert_engine）
- 业务告警规则（LLM APM）+ ops 真实指标规则（应用健康 / 日志错误突增）
- 飞书通知 webhook 可配置

### 5. 代码级自愈（ops_code_heal）
- 规则修复器（无需 LLM）+ LLM 修复引擎预留
- 补丁白名单护栏（仅 `app/ static/ tests/ requirements.txt scripts/ run.sh`）

### 6. Agent 运维对话（agent_chat）
- SSE 流式对话、Mock Agent / DeepSeek 预留
- MCP 工具（业务指标/告警/变更/CMDB/作业/日志）+ 知识库 RAG + 技能中心

### 7. /ops 一体化平台
- 11 Tab：总览/六类实体/日志/拓扑/自愈事件/配置

### 8. DevOps 资产
- `Dockerfile`（network_mode: host）、`docker-compose.yml`
- `.github/workflows/ci.yml`（GitHub Actions：lint + test + 镜像构建）
- `harness/`（Harness CI/CD 模板）
- `scripts/deploy.sh`（rsync 同步 + 依赖 + 重启 + 健康检查）

### 9. 测试
- `test_ops_api.py` / `test_ops_collector.py` / `test_self_heal.py` / `test_code_heal.py` / `test_log_collector.py`，共 34 项

---

## 三、GitHub 一键推送脚本

**对应提交**：`a2fee53 chore: 新增 GitHub 私有仓库一键推送脚本(gh create / push URL 两种模式)`

- `scripts/push_github.sh`：支持 `gh repo create` 与 push URL 两种模式，一键创建私有仓库并推送

---

## 四、/ops 页面路由修复

**对应提交**：`4058429 fix(ops): 修复 /ops 页面路由缺失，收紧页面测试断言`

- **问题**：`/ops` 一体化监控平台无法通过浏览器直接访问（路由缺失）
- **修复**：`routes_ops.py` 新增 `page_router`，提供 `/ops` 与 `/api/ops/page` 页面入口；`main.py` 挂载 `page_router`
- **测试**：页面断言收紧为严格 200 并校验 `content-type`

---

## 五、服务器部署与真实环境验证（122.51.98.98）

> 服务器：`ubuntu@122.51.98.98`；项目路径：`/home/ubuntu/neuops-agent-demo`
> 9006 业务系统（contract-compare）：`/home/ubuntu/contract-compare/backend`（systemd 托管）

### 5.1 环境实证
- SSH 连接成功，确认远程为**旧版**：无 kb 节点渲染、无 `/api/ops/*` 接口、monitor.html 无 vector_db
- 服务器 db 已有知识库数据 `kb-e56699249ea9`（经营业务），仅代码未渲染

### 5.2 同步部署
1. 备份到 `backup_deploy_<时间戳>`
2. `rsync` 同步（排除 `.venv` `*.db` `*.bin` `backup_*` `uploads` `chroma_data` `.git` `.playwright-cli` `ops.yaml` `__pycache__` `.pytest_cache` 等）
3. 安装 `psutil`、`requests`
4. 重启 9007
5. 验证通过：
   - 拓扑出现 kb 节点（知识库实体渲染成功）
   - `/api/ops/overview` 与 `/ops` 页面均 200
   - 缓存头 `Cache-Control: no-store` 生效（HEAD 405 属正常，GET 验证通过）

### 5.3 自愈演练与真相澄清
- 开启自愈：`PUT /api/ops/settings` 设置 `self_heal_enabled=1`、`self_heal_max_retry=2`、`app_9006_cwd`、`app_9006_log`
- `kill -9` 9006 进程 → 约 45 秒自动恢复
- **关键发现**：查证 incidents/alerts 后确认——9006 的恢复并非自愈引擎执行，而是 **systemd `neuops-9006.service`（Restart=always, RestartSec=3）** 自动拉起（MainPID 2452407，13:00:42 启动）
- 结论：DB 无 `restart_9006` 事件记录，自愈引擎未介入；该场景下 systemd 兜底生效
- **遗留**：自愈动作（pkill+nohup）与 systemd 托管的适配需另行安排（已列入 README 待办）

### 5.4 log_error 误报排查与修复
- **现象**：code_heal 每分钟误报"应用日志错误突增"
- **根因 A**：PID 2454057 反复绑定 9007 失败（`address already in use` 每 4 秒刷 syslog，93.5% CPU 空转）——`act_restart_self` pkill 后旧进程未完全退出的循环 → `kill -9` 清理
- **根因 B**：`log_error` 规则统计了 **system 源（syslog）** 日志，导致持续误报 → 代码修复
- **代码修复**（当前工作区未提交改动）：
  - `app/db.py`：`ops_count_logs()` 新增 `source_prefix` 参数，仅匹配 `app:` 前缀排除系统 syslog 噪音
  - `app/alert_engine.py`：`_check_ops_logs` 调用改为 `source_prefix="app:"`
  - `app/ops_self_heal.py`：verify 逻辑同样收紧
- **验证**：本地测试通过 → rsync 同步 3 个文件到服务器 → 重启 9007 → 13:07:17 后无新 `address already in use`，误报消除

---

## 六、DevOps 闭环配置（GitHub Actions CI/CD 全流程）

**目标**：形成「开发 → 测试 → 上传 → 服务器部署」全流程闭环。

| 环节 | 落地方式 | 状态 |
|---|---|---|
| 开发 | 本地 git 工作流（app/ static/ tests/ scripts/ harness/） | ✅ |
| 测试 | `pytest tests/`（36 项全绿）+ `ruff check app/` 全绿 | ✅ |
| 上传 | `git push main` → GitHub Actions CI（lint → 单测） | ✅ 配置完成 |
| 部署 | CI deploy job：SSH rsync 同步 → `remote_deploy.sh`（装依赖 → 重启 `neuops-9007` → 健康检查） | ✅ 已在服务器预演通过 |

### 关键修复与配置
1. **ci.yml 去掉 `|| true`**：原 lint/test 吞失败导致 CI 形同虚设，改为真实失败即退出
2. **ruff import 排序自动修复** + 忽略项目有意规则（`E402/E701/E702/E731/E741/F811`）
3. **修复测试时间戳缺陷**：`test_log_collector.py` 写死 `2026-08-15 10:00:00`，超出 30 分钟窗口偶发失败 → 改动态 UTC 时间戳
4. **deploy.sh 服务名修正**：`neuops` → `neuops-9007`（服务器实际 systemd 服务）
5. **deploy.sh venv 修正**：依赖安装改用 `/home/ubuntu/recon/.venv/bin/python3 -m pip install`
6. **rsync `--delete` 加固**：排除 `backup_deploy_*` / `venv`，避免误删服务器备份与运行时目录
7. **新增 `scripts/remote_deploy.sh`**：服务器端统一部署执行（装依赖 → 重启 → 健康检查），手动 / CI 共用
8. **清理服务器坏 unit**：`neuops-agent.service`（venv 失效持续 auto-restart）已 `stop + disable`
9. **CI 部署密钥**：`~/.ssh/neuops_ci_deploy`（ed25519），公钥已加入服务器 `authorized_keys`，私钥待写入 GitHub Secret `DEPLOY_SSH_KEY`

### 验证结果
- 本地：ruff 全绿，pytest 36 项全绿
- 服务器：9007 拓扑接口返回 7 类节点（hub/agent/skill/tool/server/kb/vector_db）
- CD 预演：`rsync` + `remote_deploy.sh` 完整跑通，健康检查 1 次通过

---

## 七、当前状态

- **本地**：36 项 pytest 全绿；git 已初始化（main 分支），含 3 次提交，待推送 GitHub
- **服务器**：9007 运行新代码（systemd `neuops-9007.service` 托管），kb/vector_db 拓扑、ops API、自愈演练、误报修复均已验证
- **未提交改动**：拓扑扩展（routes_monitor/monitor.html）、log_error 误报修复、manage 管理台、DevOps 闭环配置（ci.yml/deploy.sh/remote_deploy.sh/harness 文档），全部本地验证通过

### 遗留待办
| 事项 | 说明 |
|---|---|
| GitHub 推送 | 仓库创建 + secrets（`DEPLOY_SSH_KEY` 等）+ push 触发 CI/CD（需 GitHub 认证） |
| 自愈 × systemd 适配 | `restart_9006` 优先 `systemctl restart`，避免 pkill+nohup 与守护冲突（另行安排） |
| DeepSeek 联调 | 真实 LLM 对话层联调与成本控制 |
| 远程探针验证 | `PROBE_REPORT_URL` 远程上报链路 |

---

## 八、相关命令速查

```bash
# 本地测试
pytest -q

# 本地启动
python -m uvicorn main:app --host 0.0.0.0 --port 9007

# 部署服务器
./scripts/deploy.sh ubuntu@122.51.98.98 /home/ubuntu/neuops-agent-demo

# GitHub 推送
./scripts/push_github.sh <owner>/<repo> [--token xxx]
```
