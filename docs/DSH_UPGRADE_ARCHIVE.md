# NeuOps 版本存档与 DSH 升级说明

> 生成日期：2026-08-16
> 状态：**存档完成；P0–P3 已落地并部署至服务器（端到端验证通过），P4 加固待生产灰度前完成**
> 部署与验证记录：`docs/server-dsh-deploy-20260816.md`

## 1. 存档概览（双份存档）

DeepSeek Harness（DSH）重大升级前的生产版本已完成**双份存档**：

| 存档项 | 位置 | 标识 | 校验状态 |
|--------|------|------|---------|
| 本地 git tag（annotated） | GitHub 远程 `refs/tags/v1.0-pre-dsh` | 指向 `e133c525` | ✅ `git tag -v` / `ls-remote` 已验证 |
| 服务器代码备份包 | `/home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz` | 938,226 bytes / 80 条目 | ✅ `sha256sum -c` OK |
| 服务器版本指纹 | `/home/ubuntu/backup/server-version-20260816.md` | 本仓库 `docs/server-version-20260816.md` 为副本 | ✅ 已比对 |

服务器备份包放在部署目录**外**（`/home/ubuntu/backup/`），避免被 `deploy.sh` 的 `rsync --delete` 误清；包内已排除运行时数据（`*.db` / `chroma_data` / `uploads` / `__pycache__` / `backup_deploy_*`）。

## 2. 版本对照

| 维度 | 值 |
|------|-----|
| git 分支 | `main` |
| git HEAD | `e133c525eaa8ae50937e84040fe2084d697ce4fb`（工作台数字员工列表改为卡片展示） |
| tag | `v1.0-pre-dsh`（annotated，message 注明生产存档基线） |
| 服务器 | `122.51.98.98`（Ubuntu，用户 `ubuntu`） |
| 部署目录 | `/home/ubuntu/neuops-agent-demo` |
| systemd 服务 | `neuops-9007`：`active(running)`，MainPID=`2771158` |
| 启动命令 | `/home/ubuntu/recon/.venv/bin/python3 -B -m uvicorn main:app --host 0.0.0.0 --port 9007` |
| 健康接口 | `http://127.0.0.1:9007/api/ops/overview` → `{"ok":true}`，10 实体全 running |
| requirements.txt | 12 个依赖（fastapi/uvicorn[standard]/httpx/python-multipart/openpyxl/pypdf/python-docx/chromadb/fastembed/psutil/requests） |

## 3. 关键指纹值

完整清单见 `docs/server-version-20260816.md`。核心校验值：

- 备份包 sha256：`eda6e8656641300aa9ce5cdc87d6cedfa32ddf9ee35d47c1a08ab18ee8c71119`
- `requirements.txt`：`179d0425d42b556063e5b420e35b5da02892252bba6dd6ff52636cc8c7392f8f`
- `main.py`：`8bc1bb86f8aa0449c7a0784bc82857a2053d0ff390b5dad5c166eac0eed6b178`
- `app/agent_chat.py`：`c75145084a98a0f12a897bb4bf5fc2be909c1252724d8f0bba6e10ee963784ed`
- `static/index.html`：`a1d928a511f438993f04753221e0c52a9ae381754087edcfb69423829618abc0`

校验命令：

```bash
# 服务器上
sha256sum /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz   # 期望 eda6e865...
tar -tzf /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz | grep -E "(__pycache__|\.db$|chroma_data)" || echo "无运行时数据残留"
```

## 4. 生产数据说明（回退时保留，不随代码备份）

| 数据 | 路径 | 大小 |
|------|------|------|
| 会话数据库 | `/home/ubuntu/neuops-agent-demo/neuops_sessions.db` | ~33 MB |
| RAG 向量库 | `/home/ubuntu/neuops-agent-demo/chroma_data/` | ~43 MB |
| 上传目录 | `/home/ubuntu/neuops-agent-demo/uploads/` | 空 |

⚠️ 升级 / 回退操作**绝不删除或覆盖**上述数据；`deploy.sh` 的 rsync 已排除 `*.db` / `chroma_data` / `uploads`。

## 5. 回退步骤

### 5.1 代码回退（任选其一）

**方式 A：git tag 回退（本地源码，重新部署）**

```bash
cd neuops-agent-demo
git checkout v1.0-pre-dsh
./scripts/deploy.sh ubuntu@122.51.98.98 /home/ubuntu/neuops-agent-demo
```

**方式 B：服务器备份包还原（不依赖本地 git）**

```bash
# 服务器上执行（ubuntu 用户，sudo 可用）
cd /home/ubuntu
mv neuops-agent-demo neuops-agent-demo-broken      # 移走当前目录（生产数据随目录保留）
mkdir -p neuops-agent-demo
tar -xzf /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz -C /home/ubuntu --strip-components=1
# 恢复生产数据（从移走目录回拷）
mv neuops-agent-demo-broken/neuops_sessions.db neuops-agent-demo/ 2>/dev/null || true
mv neuops-agent-demo-broken/chroma_data  neuops-agent-demo/ 2>/dev/null || true
mv neuops-agent-demo-broken/uploads     neuops-agent-demo/ 2>/dev/null || true
cd /home/ubuntu/neuops-agent-demo && bash scripts/remote_deploy.sh
```

**方式 C：仅切回 legacy 引擎（DSH 升级完成后使用）**

```bash
# 服务器上：/home/ubuntu/neuops-agent-demo/app/config.py 或环境变量
# 设置 AGENT_ENGINE=legacy 后重启
sudo systemctl restart neuops-9007
```

### 5.2 回退验证

```bash
curl -fsS http://127.0.0.1:9007/api/ops/overview | head -c 120     # 期望 {"ok":true,...}
sha256sum /home/ubuntu/neuops-agent-demo/main.py                   # 期望 8bc1bb86...
sudo systemctl is-active neuops-9007                               # active
```

## 6. DSH 升级路线（P0–P3 已完成，P4 待生产部署）

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| P0 | SDK 握手验证：本机 `dsh web`（3080）+ runtime + `deepseek-v4-pro`，确认 API Key | ✅ 完成（报告见 `docs/DSH_P0_REPORT.md`） |
| P1 | 新增 `app/dsh_engine.py` + `/api/chat` 引擎分发（`AGENT_ENGINE` 开关，legacy 保留作 fallback） | ✅ 完成：双引擎可切换，前端零改动，HTTP 实测通过 |
| P2 | 新增 `dsh/neuops_tool_cli.py` 工具桥，emp-004 经营工具接入 | ✅ 完成：`tool_call`/`tool_result` 事件透传（callId 关联）实测通过 |
| P3 | emp-005/001 迁移为 DSH 子代理；`conversation` 表增加 `engine`/`dsh_session_id` 字段 | ✅ 完成：角色提示注入（`mode=skill`），落库实测通过 |
| P4 | 沙箱加固、审批白名单、回退演练 | ⏳ 见第 8 节，随生产部署落地 |

升级原则：
- 默认 `AGENT_ENGINE=legacy`，DSH 按员工灰度开启，保证一键回退；
- 每个里程碑部署前重新打 tag（如 `v1.1-dsh-p1`）；
- 升级全程不覆盖 `neuops_sessions.db` / `chroma_data`。

### 6.1 已落地实现要点（P1–P3）

- `app/dsh_engine.py`：`dsh_agent_run()` async generator，`asyncio.subprocess` 调用
  `dsh --profile headless "<task>"`（cwd=profile 目录）；完成后读取最新 headless 会话事件
  （`~/.dsh/sessions/**/session-*/session.jsonl.zstd`，zstandard 解压）透传工具事件；
  `message_end` 携带 `dsh_session_id`（会话可续接/可观测）。
- 引擎分发：`/api/chat` 的 `ChatRequest.engine`（`""`=用配置）→ `config.AGENT_ENGINE`
  （默认 `legacy`）；`engine=="dsh"` 走 `dsh_agent_run`，否则原 `mock_agent_run` 不动。
- 工具桥：`dsh/neuops_tool_cli.py` 复用 `execute_configured_tool`（mcp_tools 表配置 →
  mcp-gateway(9010) → 9006），DSH 经内置 `dsh-tool-bash` 调用，零插件开发；
  `--list-tools` / `--help-tools` 供 DSH 自主发现工具。
- 子代理化：`_build_task(mode="skill", selected_skill=...)` 注入数字员工角色身份，
  任意员工/技能对话均可 `engine=dsh` 走 DSH 内核。
- 会话落库：`conversations` 表幂等新增 `engine`/`dsh_session_id` 列（`_ensure_column`），
  `save_agent_message` 更新引擎观测字段。

## 7. 执行记录

- `2026-08-16 09:20:54` systemd `neuops-9007` 最近一次启动（部署时）
- `2026-08-16 09:44:52` 服务器打包 + 指纹生成完成（`server-version-20260816.md`）
- `2026-08-16` git tag `v1.0-pre-dsh` 推送 GitHub 成功，远程 `refs/tags/v1.0-pre-dsh^{}` = `e133c525eaa8ae50937e84040fe2084d697ce4fb`
- `2026-08-16` P0–P3 落地并本机验证（详见第 6 节）；存档时本地工作区存在未提交改动（`app/db.py`、`app/routes_employees.py`、`static/index.html`），**未纳入 tag**（tag 严格锚定已部署提交 `e133c525`）；该改动属下一迭代内容，与生产版本无关。

## 8. P4 生产加固与回退演练

### 8.1 沙箱加固（生产部署时落地）

- DSH 当前 Bash 工具以进程用户执行（`dsh-bash-local`）；生产建议切换沙箱执行：
  在 `~/.dsh/profiles/headless/package.json` 的 `bundles` 增加
  `@deepseek-ai/dsh-bash-sandbox` 与 `@deepseek-ai/dsh-sandbox`，并配置只读文件系统/网络限制。
- 工具桥 CLI（`dsh/neuops_tool_cli.py`）以只读业务查询为主（`execute_configured_tool`
  走 GET 原子只读路径）；`export_report` 等写操作需纳入审批（见 8.2）。
- 服务器需安装 Node + `@deepseek-ai/dsh`（生产引擎运行时），部署脚本需同步该依赖。

### 8.2 审批白名单

- DSH 会话事件原生含 `permission/preset`、`approval/policy` 事件——工具审批策略可在
  cordis 配置（`dsh-tool-bash` 的允许/拒绝规则）。
- 建议白名单（只读查询，直接放行）：`list_tables` / `get_table_schema` / `query_table` /
  `get_metrics` / `get_etl_metrics` / `get_contract_stats` / `get_comparison_results` /
  `query_contracts` / `query_ontology`。
- 建议审批（写操作）：`export_report`（写 Excel）、任何 `rm/mv/覆盖` 类命令。
- `AGENT_ENGINE=legacy` 为兜底：审批异常时一键切回旧引擎。

### 8.3 回退演练步骤（每个 DSH 里程碑部署前执行）

1. **前置校验**：确认备份存在且完整
   ```bash
   ssh ubuntu@122.51.98.98 'sha256sum -c <(echo "eda6e8656641300aa9ce5cdc87d6cedfa32ddf9ee35d47c1a08ab18ee8c71119  /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz")'
   ```
2. **回退执行**：按第 5 节方式 A/B/C 任选（日常迭代建议方式 A：`git checkout v1.0-pre-dsh` + 部署）。
3. **回退验证三连**：
   - `curl -fsS http://127.0.0.1:9007/api/ops/overview | head -c 120` → `{"ok":true,...}`
   - `sha256sum /home/ubuntu/neuops-agent-demo/main.py` → `8bc1bb86...`
   - `sudo systemctl is-active neuops-9007` → `active`
4. **每次里程碑部署前重新打 tag + 刷新备份**（命名如 `v1.1-dsh-p1`、`neuops-agent-demo-YYYYMMDD.tar.gz`），并把新指纹追加到 `docs/server-version-*.md`。

### 8.4 灰度开启建议

- 保持默认 `AGENT_ENGINE=legacy`；通过 `/api/chat` 请求体 `engine:"dsh"` 对单个员工/技能灰度。
- 观测落库字段（`conversations.engine` / `dsh_session_id`）评估效果后再全局切换。
- 生产部署 P1–P3 代码后，先在服务器用 `curl -X POST /api/chat -d '{"engine":"dsh"}'` 做冒烟验证，
  确认 `DSH_BIN` / `DSH_PROFILE` / zstandard 依赖均就绪（`dsh --profile headless "ok"` 返回正常）。
