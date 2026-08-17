# Design：NO-009 投标业务专家能力

> 变更：`20260817-bid-expert` | 日期：2026-08-17

## 1. 总体架构

```
static/bidding.html ──► /api/bid/* ──► app/bidding/routes_bidding.py ──► app/bidding/bid_engine.py
   (投标工作台)              │  (FastAPI 路由)        │                      ├─ 规则粗筛(章节切分)
                            │                        │                      ├─ LLM 精提炼(DeepSeek)
                            │                        │                      ├─ 生成(模板+知识库RAG)
                            │                        └─ app/db/bidding.py    └─ 自检(清单核对)
                            └─ app/db/bidding.py (bid_projects 表)
        uploads/bid/{project_id}/  规范书原文件 + outputs/ 生成成果
        app/knowledge.py           RAG 检索（5 类投标知识库，复用现有 Chroma）
```

- 复用：`app/llm`（DeepSeek 客户端）、`app/knowledge.py`（Chroma RAG）、`app/db`（SQLite、get_db）、观测体系（llm_calls/tool_calls/rag_retrievals 由既有中间件覆盖，拆标/生成调用经 `app/llm` 自动落观测表）。
- 边界：emp-007 聊天侧仅做信息问答与跳转引导；重操作全部收敛到工作台。`build_employee_tools`/`execute_configured_tool` 工具循环不改。

## 2. 数据模型（app/db/bidding.py）

`bid_projects` 表：

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK AUTOINCREMENT | 项目 ID |
| name | TEXT NOT NULL | 项目名称 |
| tenderee | TEXT | 招标方 |
| industry | TEXT | 行业 |
| budget | REAL | 预算金额（万元） |
| deadline | TEXT | 投标截止时间 |
| status | TEXT | 草稿/已上传/已拆标/已生成/已自检/已导出 |
| parse_report | TEXT(JSON) | 拆标报告 |
| generated_docs | TEXT(JSON) | 生成成果列表 [{id,type,title,path,created_at}] |
| check_result | TEXT(JSON) | 自检结果 |
| created_at / updated_at | TEXT | 时间戳 |

- 建表放 `init_db()`（与既有表同批次），迁移策略与现有 schema 一致（`CREATE TABLE IF NOT EXISTS`）。

## 3. 拆标引擎（bid_engine.py）

两段式：
1. **规则粗筛**（不依赖 LLM）：
   - 按章节标题正则切分文档（`资质|资格要求`、`业绩|案例|类似项目`、`技术参数|技术需求|货物需求`、`评分|评审标准|评标办法`、`废标|否决|无效投标|★|▲`）。
   - 对每个章节抽 3–5 个候选句（首句/含关键词句），产出六类骨架，缺项填「未识别」。
2. **LLM 精提炼**：章节文本分块（约 4000 字符/块，500 页级支持）喂 DeepSeek，按固定 JSON Schema 输出六类结构化条目；解析失败或网络异常时回退到规则粗筛结果。
- 输出落 `parse_report` 字段；状态流转「已上传→已拆标」。

## 4. 生成引擎（bid_engine.py）

- 输入：拆标报告 + RAG 检索（`app/knowledge.py`，按素材/模板/资质/业绩/人员 5 库检索）+ 内置模板。
- 输出四类：
  - `tech_proposal` 技术方案建议书
  - `response` 招标点对点应答（逐条对照拆标报告应答清单）
  - `ppt_outline` 售前汇报 PPT 大纲
  - `impl_plan` 运维实施方案
- 规则：拆标报告有依据的项直接生成；无依据项输出「【待补充材料】xxx」占位，不编造参数。
- 生成文本落盘 `uploads/bid/{project_id}/outputs/{doc_id}.md`，记录到 `generated_docs`。

## 5. 合规自检（bid_engine.py）

对生成材料文本 + 拆标报告执行：
- 未响应项清单：对照应答清单逐条检查生成文本是否覆盖（关键词命中）。
- 废标红线提示：对拆标报告的 `rejection_clauses` 逐条检查是否在文本中有应对说明。
- 评分点得分建议：对 `scoring` 逐条按覆盖度给出 0~满分 的建议得分。
- 结果存 `check_result`；状态流转「已生成→已自检」。

## 6. 导出

- md：直接返回文件。
- docx：用 `python-docx`（新依赖，加入 `requirements.txt`）从 md 文本渲染（标题/段落/表格），`BytesIO` 返回 `StreamingResponse`。

## 7. 前端（static/bidding.html）

单页应用（原生 JS + fetch），两个视图：
- 项目列表：新建按钮 + 表格（名称/招标方/行业/预算/截止/状态/操作）。
- 项目详情：信息编辑、上传区（多文件）、规范书列表、拆标报告展示（六类卡片）、生成面板（四类按钮 + 结果预览）、自检结果区、导出按钮。
- 样式与 `static/index.html` 统一（深色侧边栏 + 浅色内容区风格）。

## 8. 聊天联动（agent_chat.py）

- `_emp_meta["emp-007"]` 的 `open_url` 改为 `http://127.0.0.1:9007/bidding`。
- `build_employee_prompt` 对 emp-007 追加行为指引段（数据驱动：`emp_id == "emp-007"` 时拼接），说明信息问答 vs 重操作跳转边界。

## 9. 知识库预置（seed_data.py + mock_data.py + db/kb.py）

- 5 类库：`bid-qualification`（资质）、`bid-performance`（业绩）、`bid-material`（素材）、`bid-template`（模板）、`bid-staff`（人员）。
- `mock_data.py` 扩展每类 1–2 条示例文档 → 向量化写入 Chroma（复用现有知识库写入函数）。
- `db_bind_employee_kb("emp-007", [5 库 id])` 替换现有单一绑定（复用现有绑定函数）。

## 10. 风险与回退

- LLM 不可用：拆标回退规则粗筛骨架（TC-2）；生成/自检返回明确错误提示，不阻塞页面。
- 上传格式：docx（python-docx）/pdf（PyPDF2）/xlsx（openpyxl）/txt，均在 `app/bidding` 内独立解析，不依赖外部服务。
