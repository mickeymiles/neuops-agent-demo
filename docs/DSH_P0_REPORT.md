# DSH P0 验证报告（SDK 握手）

> 日期：2026-08-16
> 状态：✅ **全部通过**

## 1. 验证结论摘要

| # | 验证项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | DSH runtime（dsh web 调试台） | ✅ 运行中 | `node` PID 97944 监听 `127.0.0.1:3080`，HTTP 200 |
| 2 | API Key 配置 | ✅ 已配置 | `~/.dsh/.credentials.yaml` → `DEEPSEEK_API_KEY`（`sk-991ed***0d48`，掩码） |
| 3 | 模型可用性 | ✅ 两个模型均存在 | `GET api.deepseek.com/v1/models` → `deepseek-v4-pro`、`deepseek-v4-flash` |
| 4 | `deepseek-v4-pro` 实际调用 | ✅ 可调用 | chat/completions 返回 `model: deepseek-v4-pro` |
| 5 | headless 引擎端到端 | ✅ 真实完成任务 | `dsh --profile headless "回复两个字：握手成功"` → 输出 `握手成功`，exit 0 |

## 2. 架构认知（关键修正）

原计划假设「deepseek-harness-sdk（Python SDK）」为集成方式。**实测 DSH 为 Node.js/npm 技术栈**：

- 主包：`@deepseek-ai/dsh` **v0.1.0-rc.6**（`bin: dsh`），cordis 插件框架
- 全量插件位于 npx 缓存：`~/.npm/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/*`
- 关键插件（与生产集成直接相关）：
  - `dsh-headless`：一次性任务执行（提交单任务 → 等待停稳 → 最后一条 assistant 文本写 stdout → exit 0/1，**不监听端口**）→ **生产引擎首选**
  - `dsh-tool-bash` / `dsh-bash-sandbox`：Bash 工具与沙箱 → **工具桥方案基础**
  - `dsh-subagent`：子代理 → emp-005/001 迁移
  - `dsh-session-query-sqlite`：会话查询（SQLite）→ 会话落库
  - `dsh-mcp-client`：MCP 客户端 → 工具协议正式化
  - `dsh-llm-deepseek`：DeepSeek LLM 后端

## 3. 生产集成形态（P1 依据）

```
FastAPI (9007) /api/chat
   └─ asyncio subprocess ──> dsh --profile headless "<task>"
        ├─ stdout: 最终 assistant 文本
        ├─ 事件流：通过 dsh 的 session/事件持久化（JSONL/SQLite）读取 wire order 事件
        │          或 dsh web 调试台 WebSocket 通道（3080）
        └─ 工具：dsh-tool-bash 调用 dsh/neuops_tool_cli.py（9007 工具接口 CLI 封装）
```

## 4. 环境事实

- 本机（macbook）：`dsh web`（3080）已运行；`~/.dsh/profiles/headless` 已创建（bundles: `dsh-base` + `dsh-headless`），实测可执行任务
- 服务器（122.51.98.98）：**未安装 Node/dsh**，P1 需在服务器安装（Node + `@deepseek-ai/dsh`），或先在本机完成引擎开发，部署时同步
- 模型分层建议：主 agent `deepseek-v4-pro`，快速技能 `deepseek-v4-flash`

## 5. 遗留确认项

- headless 事件流透传（agent_thought/tool_call/tool_result）需在 P1 通过 session 事件持久化或 3080 通道实测；计划中「on_notification 回调」为 Python SDK 假设，Node 形态下改为**读取会话事件区间**（headless runner 已实现「汇总持久化事件区间」逻辑，可复用思路）
- `dsh --profile headless` 单任务模式天然契合 `/api/chat` 单轮 SSE 流式；多轮需会话续接（`--resume <session>`），P3 处理
