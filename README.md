# NeuOps 一体化运维监控平台（Agent Demo）

> 基于本体的一体化实时监控 · 统一探针采集 · Agent 运维对话

NeuOps 是一个可运行的运维监控平台 Demo：内置统一监控探针（六类真实采集 + 应用日志采集）、运维本体拓扑、告警引擎、知识库检索与 Agent 对话，并提供 `/ops` 一体化运维监控页面。

默认端口 `9007`。

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          前端（static/）                          │
│   index.html（运维工作台） monitor.html（LLM APM） ops.html（一体化）│
│   knowledge.html（知识库） share.html（分享页） traditional/       │
└───────────────────────────────┬──────────────────────────────────┘
                                │ HTTP /api/*（FastAPI 薄入口 main.py）
┌───────────────────────────────┴──────────────────────────────────┐
│                      后端应用层（app/ 领域包）                     │
│  agent_chat（Agent 对话/SSE）  routes_*（业务路由）                │
│  alert_engine（告警引擎）      ops_ontology（运维本体）            │
│  knowledge（知识库/向量检索）   mcp_tools（MCP 工具）              │
│  devtools（文件/开发工具）      feishu_notify（飞书通知）          │
│  traditional_pages（传统页面）  mock_data（种子/模拟数据）          │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────┴──────────────────────────────────┐
│               统一监控探针（app/probe/，周期 30s 后台采集）        │
│  server_collector  container_collector  database_collector        │
│  middleware_collector  application_collector  network_collector   │
│  log_collector（增量 tail 应用日志）                               │
└───────────────────────────────┬──────────────────────────────────┘
                                │ 写入
┌───────────────────────────────┴──────────────────────────────────┐
│                       数据层（本地持久化）                        │
│  neuops_sessions.db（SQLite：实体/指标/日志/告警/会话）           │
│  chroma_data/（知识库向量库）  uploads/（上传文档）                │
└──────────────────────────────────────────────────────────────────┘
```

**整体流程（数据闭环）：**

```
探针采集 → SQLite（实体/时序指标/日志）
   → 告警引擎（ops 真实指标 + 日志错误）→ alerts + 飞书通知
   → 本体拓扑（五类实体 + 三类关系）→ /ops 可视化
   → Agent 对话（SSE 流式 + MCP 工具 + 知识库检索）
```

---

## 二、目录结构

```
neuops-agent-demo/
├── main.py                    # 薄入口：组装 app / 挂载路由 / 初始化 DB / 启动探针
├── seed_data.py               # 种子数据（技能/员工/会话/MCP 映射），启动时导入
├── mcp_gateway.py             # MCP 工具网关（端口 9010，DATA_SOURCE=mock|real）
├── requirements.txt           # 依赖清单
├── Dockerfile                 # 容器化（network_mode: host 访问本机 9006 等）
├── docker-compose.yml         # host 网络编排
├── ops.yaml                   # /ops 页面结构快照（验证用，gitignore）
├── app/                       # 后端领域包
│   ├── config.py              # 全局配置：路径/端口/探针周期/阈值/白名单
│   ├── db.py                  # SQLite 数据层（会话/配置/运维实体/指标/日志/告警）
│   ├── agent_chat.py          # Agent 对话链路（Mock Agent / DeepSeek / SSE）
│   ├── alert_engine.py        # 业务告警检测引擎（LLM APM + ops 真实指标 + 日志错误）
│   ├── ops_ontology.py        # 运维本体：五类实体 + 三类关系
│   ├── knowledge.py           # 知识库：文档入库 / 向量检索 / 问答
│   ├── mcp_tools.py           # MCP 原子工具（业务指标/告警/变更/CMDB/作业/日志）
│   ├── devtools.py            # 研发专家工具（9006 代码库读文件/搜索等）
│   ├── feishu_notify.py       # 飞书告警通知（webhook 可配置）
│   ├── traditional_pages.py   # 传统页面（employees/tasks 等）
│   ├── routes_*.py            # 各领域 API（workspace/monitor/ops/knowledge/employees/tasks）
│   └── probe/                 # 统一监控探针（六类采集 + 日志采集 + CLI）
│       ├── manager.py         # 探针调度器（30s 周期、手动采集、远程上报入口）
│       ├── base.py            # 采集器基类
│       ├── *_collector.py     # 服务器/容器/数据库/中间件/应用/网络 采集器
│       ├── log_collector.py   # 应用日志增量采集
│       └── cli.py             # 探针独立 CLI（单次采集/持续采集）
├── static/                    # 前端
│   ├── ops.html               # /ops 一体化运维监控平台（11 Tab）
│   ├── monitor.html           # LLM APM 监控页
│   ├── index.html             # 运维工作台（对话）
│   ├── knowledge.html         # 知识库页
│   ├── share.html             # 分享页
│   ├── ops.css                # /ops 样式
│   └── traditional/ vendor/   # 传统页面 / 第三方资源
├── tests/                     # 32 项 pytest
│   ├── test_ops_api.py        # ops API（总览/实体/拓扑/设置/告警规则）
│   ├── test_ops_collector.py  # 六类采集器
│   └── test_log_collector.py  # 日志采集
├── harness/                   # Harness CI/CD 模板（gitops / cd）
├── .github/workflows/ci.yml   # GitHub Actions CI（lint + test + 镜像构建）
└── scripts/                   # 运维脚本
    ├── deploy.sh              # 服务器部署（rsync + 依赖 + 重启 + 健康检查）
    ├── push_github.sh         # GitHub 私有仓库一键推送
    ├── init_ops.py            # 初始化运维数据
    ├── build_kb.py            # 构建知识库
    ├── update_mock.py         # 更新模拟数据
    └── split_refactor.py      # 代码拆分重构工具
```

---

## 三、核心能力

### 1. 统一监控探针（app/probe/）
- 六类真实采集：**服务器 / 容器 / 数据库 / 中间件 / 应用 / 网络**（psutil + 真实命令 + 端口/进程识别）
- 应用日志增量采集（tail，可配置日志路径与错误阈值）
- 后台线程周期调度（默认 30s），支持手动采集与远程探针上报（CLI / HTTP ingest）
- 实体自动注册、时序指标写入 SQLite、按天自动清理

**远程探针（多服务器纳管）**：将 `app/probe` 部署到目标机，通过
`--report-http http://监控中心:9007/api/ops/probe/ingest` 上报，与监控中心采用完全相同的六类采集逻辑。
上报数据按主机名（scope）隔离存储：实体/关系只重建该主机自身的数据，本机与各远程机互不覆盖；
指标自动参与既有告警规则（服务器 CPU/内存/磁盘/健康检查）；远程日志 source 带主机前缀避免与本机规则混用；
远程服务器告警升级为人工处置。部署：

```bash
# 免密 SSH（推荐）
./scripts/deploy_remote_probe.sh ubuntu@目标机IP

# 账号密码（本机需装 sshpass，密码经 SSHPASS 环境变量传入，不出现在命令行）
SSHPASS='你的密码' ./scripts/deploy_remote_probe.sh ubuntu@目标机IP
```

脚本为幂等部署：目标机缺 `python3-venv` 时自动 apt 补齐并重建 venv；unit 文件由脚本内生成，
已部署过的机器可重复执行以更新探针代码（`rsync --delete` 同步 + `systemctl restart`）。

### 2. 运维本体（ops_ontology）
- 五类实体：server / database / network / container / middleware / application（六类采集实体）
- 三类关系：依赖 / 部署 / 包含，生成拓扑图
- 提供 `/api/ops/topology` 拓扑接口与前端可视化

### 3. 告警引擎（alert_engine）
- 业务告警规则（LLM APM 模拟）+ ops 真实指标规则（应用健康、日志错误突增）
- 告警规则可在 `/ops` 配置中心增删改查
- 日志错误统计仅统计 `app:` 源日志，排除系统 syslog 噪音
- 支持飞书 webhook 通知（页面可配置）

### 4. Agent 运维对话（agent_chat）
- SSE 流式对话，Mock Agent 执行链路 / DeepSeek 真实 LLM 调用（预留）
- MCP 工具：业务指标 / 告警查询 / 变更记录 / CMDB 拓扑 / 自动作业 / 服务日志
- 技能中心：服务故障根因分析 / 告警关联变更排查 / 业务集群巡检 / 工单智能处置 等
- 知识库检索增强（RAG）

### 5. /ops 一体化运维监控平台
`http://localhost:9007/ops`，11 个 Tab：总览 / 服务器 / 数据库 / 网络 / 容器 / 中间件 / 应用 / 日志 / 本体拓扑 / 告警中心 / 配置

---

## 四、快速开始

### 本地运行

```bash
# 1. 准备虚拟环境（Python 3.11+）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动（首次自动建库 + 导入种子数据 + 启动探针/引擎）
python -m uvicorn main:app --host 0.0.0.0 --port 9007

# 3. 访问
#    /ops            一体化运维监控平台
#    /               Agent 运维工作台
#    /docs           FastAPI 交互文档
```

### Docker

```bash
docker compose up -d --build   # network_mode: host，需宿主机可访问 127.0.0.1:9006
curl http://127.0.0.1:9007/api/ops/overview
```

### 运行测试

```bash
pytest -q          # 34 项全绿
```

### 部署到服务器

```bash
./scripts/deploy.sh ubuntu@<host> /home/ubuntu/neuops-agent-demo
# 等价于：rsync 同步 → 安装依赖 → 重启（systemd/nohup）→ 健康检查 /api/ops/overview
```

---

## 五、主要 API（/api/ops/*）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/ops/overview` | 总览（探针状态/实体/告警/服务器快照） |
| GET | `/api/ops/entities` | 实体列表（按类型过滤） |
| GET | `/api/ops/entities/{id}` | 实体详情 |
| GET | `/api/ops/topology` | 本体拓扑 |
| GET | `/api/ops/metrics` | 时序指标 |
| GET/PUT | `/api/ops/settings` | 配置中心（阈值/日志路径等） |
| GET/POST/PUT/DELETE | `/api/ops/alert-rules` | 告警规则管理 |
| GET | `/api/ops/logs` | 日志查询 |
| GET/POST | `/api/ops/probe/status` `/run-now` `/ingest` | 探针状态 / 手动采集 / 远程上报 |
| GET | `/api/ops/page` `/ops` | 一体化监控页面 |

---

## 六、关键配置（app/config.py）

| 配置 | 默认 | 说明 |
|---|---|---|
| `PORT` | `9007` | 服务端口 |
| `OPS_PROBE_INTERVAL` | `30` | 探针采集周期（秒） |
| `OPS_RETENTION_DAYS` | `1` | 指标保留天数 |
| `LOG_ERROR_WINDOW_MIN` | `5` | 日志错误统计窗口（分钟） |
| `LOG_ERROR_THRESHOLD` | `10` | 日志错误告警阈值 |
| `APP_9006_*` | `http://127.0.0.1:9006` | 9006 业务系统健康检查 |
| `MIDDLEWARE_PROBES` | redis/mysql/pg/nginx/rabbitmq/kafka/es/mongo | 中间件探测候选 |
| `PROBE_REPORT_URL` | `` | 远程探针上报地址（CLI `--report-http` 直接指定，无需环境变量） |

---

## 七、DevOps

- **CI（GitHub Actions）**：`.github/workflows/ci.yml` — ruff lint + pytest + Docker 构建推送 GHCR
- **CD（Harness 模板）**：`harness/` — gitops / cd pipeline 模板（集成 deploy.sh）
- **Docker**：`Dockerfile` + `docker-compose.yml`（host 网络，访问宿主机 9006/9007 服务）
- **一键推送**：`scripts/push_github.sh`（gh create / push URL 两种模式）

---

## 八、项目状态与路线

**已完成**
- [x] 统一探针六类真实采集 + 应用日志采集
- [x] 运维本体拓扑与可视化
- [x] 告警引擎（ops 指标 + 日志错误，修复 syslog 噪音误报）
- [x] /ops 一体化平台（11 Tab）与 /ops 路由修复
- [x] Agent 对话（SSE + MCP 工具 + 知识库 RAG）
- [x] 32 项 pytest 全绿 + 本地端到端验证
- [x] 服务器部署（rsync/deploy.sh）与真实环境验证（探针/kb 渲染）
- [x] CI / Docker / Harness 模板 / GitHub 推送脚本
- [x] 自愈（self-heal）与代码修复（code heal）功能整体移除

**待办（另行安排）**
- [ ] 清理服务器遗留的 `neuops-agent.service` 坏 unit（venv 路径失效，持续 auto-restart）
- [ ] DeepSeek 真实 LLM 对话层联调与成本控制
- [x] 远程探针（PROBE_REPORT_URL）部署到目标机验证（scope 隔离 + 日志上报）
