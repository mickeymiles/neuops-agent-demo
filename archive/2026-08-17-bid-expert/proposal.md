# 变更提案：NO-009 投标业务专家能力补齐（投标工作台 + 拆标/生成/自检 + 聊天联动）

> 变更编号：`20260817-bid-expert`
> 作者：售前数字化小组 | 日期：2026-08-17 | 状态：已批准
> 涉及规格：NO-009（新增）、NO-006（MODIFIED，emp-007 行为指引）、NO-008（MODIFIED，知识库预置与绑定）

## 背景与问题

- emp-007「售前投标方案智能组装专家」已具备技能定义（skill-21）与知识库绑定（售前知识库-历史方案与中标库），但**缺少可落地的重操作承载**：用户无法上传规范书、触发拆标、生成应答、合规自检与导出文档，能力停留在聊天问答。
- 存量聊天交互适合"信息获取与业务沟通"（知识库问答、政策解读、经验咨询），不适合承载上传/拆标/生成等重型操作。
- 业界对标：76% 废标源于非技术性错误（漏项、未响应、红线违规）→ 拆标不漏项 + 合规自检是价值核心。

## 目标

1. 提供投标工作台（`/bidding`），实现"项目管理 → 上传规范书 → 拆标解析 → 生成材料 → 合规自检 → 成果导出"完整链路。
2. 聊天与工作台分工明确：信息类问答留在聊天；重操作由 emp-007 引导跳转工作台。
3. 复用现有 Agent 引擎、知识库（Chroma）、MCP 工具网关与观测体系（llm_calls/tool_calls/rag_retrievals），模块化落位于 `app/bidding/`，未来可拆分。

## 变更范围

### In Scope

- 新增 `app/bidding/` 子包：`routes_bidding.py`（API）+ `bid_engine.py`（拆标/生成/自检/导出核心逻辑）
- 新增 `app/db/bidding.py`：`bid_projects` 表（元数据 + 拆标报告 JSON + 成果记录）
- 新增 `static/bidding.html` 投标工作台页面；`static/index.html` 侧边栏入口
- `main.py` 挂载路由；`uploads/bid/{project_id}/` 存放规范书与成果
- 拆标：规则粗筛章节切分 + DeepSeek 按 JSON Schema 精提炼（FR-3）
- 生成：拆标报告 + 知识库 + 模板 → 技术方案/点对点应答/PPT大纲/实施方案（FR-4）
- 自检：未响应项清单 / 废标红线提示 / 评分点得分建议（FR-5）
- 导出：docx / markdown 下载（FR-6）
- emp-007 聊天联动：`open_url` 指向 `/bidding`；prompt 追加"信息问答 vs 跳转工作台"行为指引（FR-7）
- 知识库：预置 5 类库（资质/业绩/素材/模板/人员），每类 1–2 条示例数据，绑定 emp-007（FR-8 新增于 NO-008 delta）
- pytest 用例（标注 `# NO-009 FR-x`）+ TRACEABILITY 更新 + 归档

### Out of Scope

- 不在聊天内做拆标/生成/上传（重操作一律跳转工作台）
- 不接入真实政府采购平台/招投标网站
- 不做多人协作、权限、审批流
- 不修改 emp-007 现有工具循环（`build_employee_tools`/`execute_configured_tool` 逻辑不变）

## 接口与数据契约

### API 一览（`/api/bid/*`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bid/projects` | 项目列表 |
| POST | `/api/bid/projects` | 新建项目 |
| GET | `/api/bid/projects/{pid}` | 项目详情（含拆标报告/成果） |
| PATCH | `/api/bid/projects/{pid}` | 更新项目信息/状态 |
| DELETE | `/api/bid/projects/{pid}` | 删除项目 |
| POST | `/api/bid/projects/{pid}/upload` | 上传规范书（docx/pdf/xlsx/txt，多文件） |
| GET | `/api/bid/projects/{pid}/files` | 规范书文件列表 |
| POST | `/api/bid/projects/{pid}/parse` | 触发拆标（返回结构化报告） |
| POST | `/api/bid/projects/{pid}/generate` | 生成材料（type: tech_proposal/response/ppt_outline/impl_plan） |
| POST | `/api/bid/projects/{pid}/check` | 合规自检 |
| GET | `/api/bid/projects/{pid}/export/{doc_id}?fmt=docx\|md` | 导出成果文档 |

### 拆标报告 JSON 结构（`bid_projects.parse_report`）

```json
{
  "qualifications": [{"item": "xx资质", "level": "xx级", "required_docs": ["证书复印件"], "source": "章节/页码"}],
  "performance": [{"item": "近3年同类业绩", "requirement": "≥2个", "evidence": "合同/验收报告"}],
  "tech_params": [{"item": "CPU主频", "value": "≥3.0GHz", "acceptance": "提供产品彩页", "is_key": true}],
  "scoring": [{"item": "技术方案完整性", "score": 20, "notes": "评分点说明"}],
  "rejection_clauses": ["未按格式密封", "关键参数负偏离"],
  "response_checklist": [{"id": "R1", "item": "资质证书复印件", "doc_type": "证明文件", "status": "todo"}]
}
```

## 涉及规格条目

- **ADDED**：NO-009 投标业务专家能力（FR-1 ~ FR-7、NFR-1、TC-1）
- **MODIFIED**：NO-006 追加 FR（emp-007 重操作跳转工作台行为指引）
- **MODIFIED**：NO-008 追加 FR（预置 5 类投标知识库并绑定 emp-007）

## 验收标准

- [ ] `cd neuops-agent-demo && pytest -q` 全量通过（新增 `tests/test_bid.py`，标注 `# NO-009 FR-x`）
- [ ] 启动后 `/bidding` 可访问，侧边栏含"投标工作台"入口
- [ ] 工作台可完成：新建项目 → 上传规范书 → 拆标（输出六类结构化报告，缺项标"未识别"）→ 生成四类材料 → 合规自检（未响应/红线/评分建议）→ 导出 docx/md
- [ ] 聊天中 emp-007 对"上传/拆标/生成"类请求回复跳转 `/bidding` 指引；信息类问题（资质要求/评分标准解读）在聊天内回答
- [ ] 5 类投标知识库已创建且绑定 emp-007，每类含 1–2 条示例数据
- [ ] 更新 `specs/TRACEABILITY.md` 并归档本变更目录

## 风险与兼容性

- 拆标依赖 DeepSeek LLM 调用（复用 `app/llm` 层）；网络不可用时规则粗筛仍产出兜底章节结构（缺项标"未识别"），不阻塞流程。
- 新增 `bid_projects` 表与既有表无冲突；`db_bind_employee_kb` 复用现有实现，不破坏既有员工绑定。
- emp-007 prompt 追加行为指引为纯增量，不影响其他 emp 的 prompt 生成逻辑。
- 页面走 `/static/bidding.html`，`no_cache_static` 中间件已覆盖，无缓存问题。
