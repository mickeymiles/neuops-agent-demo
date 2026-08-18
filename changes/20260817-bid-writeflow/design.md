# 设计：投标工作台 SOP 化分步编写流程

> 变更编号：`20260817-bid-writeflow`
> 日期：2026-08-17 | 状态：草案

## 技术方案

生成链路从「一键规则拼装」升级为「LLM 驱动的 6 步 SOP 流水线」：

1. **项目知识库**：新增 `_ensure_project_kb(pid)`（幂等创建 `bid-project-{pid}`）、
   `_kb_write_text(pid, name, text)`（复用 `db_create_knowledge_base` +
   `build_kb_index`/`db_add_kb_chunks`），上传/拆标/模板三处调用。
2. **LLM 封装**：复用 `_call_llm_json`（DeepSeek，配置 `DEEPSEEK_API_KEY`），
   所有新能力统一走该封装；失败时降级规则模板（`_fallback_*`）。
3. **新增生成函数**：`requirements_analysis`、`generate_mockup`、`generate_outline`、
   `generate_chapter`、`assemble_document`，各自独立 LLM 调用。
4. **章节存储**：`outputs/bid/{pid}/chapters/{index}.md` + SQLite 记录章节确认状态。
5. **前端**：6 步步骤条、全屏 loading 遮罩、左右对照编辑器、`doGenerate` 刷新修复、
   拆标卡片滚动条。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `app/bidding/bid_engine.py` | 新增 5 个 LLM 生成函数 + 项目知识库辅助 + 降级模板 |
| `app/bidding/routes_bidding.py` | 新增 5 个路由；upload/parse/template 追加入库 |
| `app/db/bidding.py` | 新增 chapters 记录读写 |
| `app/knowledge.py` | 复用 build_kb_index，无改动（若需按文本写入则补充 db_add_kb_chunks 调用） |
| `static/bidding.html` | 步骤条、loading 遮罩、左右对照编辑器、刷新修复、滚动条 |
| `tests/test_bid.py` | 新增用例标注 `# NO-009 FR-16/17/18/19/20/21` |

## 数据模型变更

- SQLite `bid_projects` 表新增字段（经迁移函数 `_migrate` 幂等补列）：
  - `prd_json TEXT`（需求分析 PRD）
  - `outline_json TEXT`（章节大纲）
  - `chapters_json TEXT`（章节列表与确认状态：title/content/confirmed/source）
- 文件系统：`outputs/bid/{pid}/chapters/{index}.md`、`outputs/bid/{pid}/mockup.html`

## 兼容性说明

- 既有 `/generate` 接口保持原响应结构（doc 记录），内部可复用分步能力
- 预置 5 类投标库不受影响；项目知识库独立命名空间
- 未配置 `DEEPSEEK_API_KEY` 时全部新能力降级规则模板，流程不中断
