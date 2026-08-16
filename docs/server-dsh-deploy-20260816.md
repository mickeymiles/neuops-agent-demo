# NeuOps 服务器 DSH 引擎部署与验证记录 20260816

> 生成时间: 2026-08-16 10:20 CST
> 部署对象: ubuntu@122.51.98.98，服务 neuops-9007
> 部署基线: 本地 git tag `v1.1-dsh-p1`（HEAD=`e133c525` + P1–P3 DSH 代码）
> 前置存档: tag `v1.0-pre-dsh` / 备份包 `/home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz`（sha256 `eda6e865...`）

## 1. 结论先行

**服务器需要安装 DeepSeek Harness。** `app/dsh_engine.py` 通过 subprocess 直接调用 `dsh` CLI（Node.js 技术栈），headless 会话与凭据存储在 `~/.dsh/`；默认 `AGENT_ENGINE=legacy` 不依赖 DSH（回退安全），但员工灰度切换 `engine:"dsh"` 后必须 DSH 可用。

本次已全部部署并通过端到端验证：DSH 引擎可正常调用模型、可经工具桥查询 **9006 真实经营数据**、会话观测字段正确落库。

## 2. 服务器 DSH 环境

| 项 | 值 |
|----|-----|
| Node.js | v22.22.3（npm 10.9.8，系统预装） |
| DSH 包 | `@deepseek-ai/dsh@0.1.0-rc.6`（npm 全局，用户级 prefix） |
| dsh 可执行 | `/home/ubuntu/.npm-global/bin/dsh` |
| 凭据 | `/home/ubuntu/.dsh/.credentials.yaml`（`DEEPSEEK_API_KEY`，chmod 600） |
| headless profile | `/home/ubuntu/.dsh/profiles/headless/`（bundles: dsh-base + dsh-headless） |
| 会话存储 | `/home/ubuntu/.dsh/sessions/**/session-*/session.jsonl.zstd` |

安装命令（用户级 prefix，避免 `/usr/lib/node_modules` 权限问题）：
```bash
npm i -g --prefix $HOME/.npm-global @deepseek-ai/dsh@0.1.0-rc.6
```

首次握手验证：`~/.npm-global/bin/dsh --profile headless '请只回复：握手成功'` → 输出 `握手成功`。

## 3. 服务配置变更

systemd drop-in（不动原 unit 文件）：
```ini
# /etc/systemd/system/neuops-9007.service.d/dsh.conf
[Service]
Environment=DSH_BIN=/home/ubuntu/.npm-global/bin/dsh
```
执行：`systemctl daemon-reload && systemctl restart neuops-9007`
验证：`systemctl show neuops-9007 -p Environment` → 含 `DSH_BIN=/home/ubuntu/.npm-global/bin/dsh`。

> `_resolve_dsh_bin()` 查找顺序：`DSH_BIN` env → PATH `which dsh` → `~/.npm/_npx/*/node_modules/.bin/dsh`。本机为 npx 缓存方式（第三个分支命中），服务器用 `DSH_BIN` 显式指定，两者皆可。

## 4. 同步文件清单（本机 → 服务器）

| 文件 | 类型 | 说明 |
|------|------|------|
| `app/dsh_engine.py` | 新增 | DSH 引擎（SSE 透传 + headless 会话解析） |
| `app/agent_chat.py` | 修改 | `/api/chat` 引擎分发 + 落库观测字段 |
| `app/db.py` | 修改 | conversations 表 `engine`/`dsh_session_id` 幂等补列 |
| `app/config.py` | 修改 | `AGENT_ENGINE`/`DSH_BIN`/`DSH_PROFILE`/`DSH_TIMEOUT`/`DSH_HOME` |
| `app/mcp_tools.py` | 修改 | `ChatRequest.engine` 字段 |
| `dsh/neuops_tool_cli.py` | 新增 | 工具桥（复用 `execute_configured_tool` → 9010 mcp-gateway → 9006） |
| `requirements.txt` | 修改 | 追加 `zstandard`（已装 0.25.0 到 `/home/ubuntu/recon/.venv`） |
| `docs/DSH_P0_REPORT.md` / `docs/DSH_UPGRADE_ARCHIVE.md` | 新增/更新 | 文档归档 |

同步前备份：`/home/ubuntu/backup/pre-dsh-sync-20260816/app_pre.tar.gz`（agent_chat/db/config/mcp_tools + requirements，35,102 bytes）。

## 5. 端到端验证结果（全部通过）

| # | 验证项 | 请求 | 结果 |
|---|--------|------|------|
| 1 | 健康检查 | `GET /health` | `{"status":"ok","service":"NeuOps Agent Demo"}` |
| 2 | legacy 回归 | `POST /api/chat` `{"engine":"legacy"}` | SSE 正常（agent_thought/route/tool_call），不受 DSH 影响 |
| 3 | DSH 引擎 | `POST /api/chat` `{"engine":"dsh","query":"请只回复：DSH服务器验证OK"}` | `agent_thought` → `agent_message`("DSH服务器验证OK") → `message_end`（带 `dsh_session_id=68376932-...`） |
| 4 | 工具桥端到端 | `POST /api/chat` `{"engine":"dsh","query":"查询毛利率最近三年..."}` | DSH 经 Bash 调 `neuops_tool_cli.py get_etl_metrics`（3 组 tool_call/tool_result），返回 **9006 真实数据**：2024=5.04% / 2025=4.90% / 2026=6.18%（含未完整年度提示） |
| 5 | 会话落库 | sqlite 查询 conversations | `engine='dsh'`、`dsh_session_id='fcc8fc0d-...'` 等已写入 |
| 6 | 会话文件 | `~/.dsh/sessions/` | `session-<dsh_session_id>/session.jsonl.zstd` 生成，与落库 ID 一一对应 |

服务日志：`journalctl -u neuops-9007` 无 error/traceback，仅正常访问日志。

## 6. 灰度与回退

**灰度方式**：保持 `AGENT_ENGINE=legacy`（默认），按员工在请求体传 `engine:"dsh"` 逐步开放；或设置全局 `Environment=AGENT_ENGINE=dsh` 全量切换。

**回退步骤**：
1. 还原代码：`tar xzf /home/ubuntu/backup/pre-dsh-sync-20260816/app_pre.tar.gz -C /home/ubuntu/neuops-agent-demo`
2. 移除 drop-in：`rm /etc/systemd/system/neuops-9007.service.d/dsh.conf && systemctl daemon-reload`
3. 重启：`systemctl restart neuops-9007`
4. 验证：`curl http://127.0.0.1:9007/health`；legacy 请求正常即回退完成。
5. （可选）卸载 DSH：`npm uninstall -g --prefix $HOME/.npm-global @deepseek-ai/dsh`，删除 `/home/ubuntu/.dsh`。

## 7. 遗留说明

- 工具桥依赖 mcp-gateway(9010) 与业务后端(9006)，两服务保持运行；若 9010 不可用，DSH 任务中的工具调用将失败（DSH 会重试/报错，legacy 不受影响）。
- 沙箱加固（`dsh-bash-sandbox`）、审批白名单、回退演练详见 `docs/DSH_UPGRADE_ARCHIVE.md` 第 8 节，建议生产灰度前完成。
