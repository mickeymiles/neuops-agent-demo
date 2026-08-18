# 投标业务专家能力 Specification

> 规格编号: NO-009 | 状态: 生效 | 最后更新: 2026-08-18
> 对应代码: `app/bidding/routes_bidding.py`、`app/bidding/bid_engine.py`、`app/db/bidding.py`、`static/bidding.html`

## Purpose

提供投标业务专家能力：投标工作台支撑"项目管理 → 规范书上传 → 拆标解析 → 生成材料 → 合规自检 → 成果导出"完整链路；聊天侧 emp-007 仅承接信息问答，重操作引导跳转工作台。

## Requirements

### Requirement: 投标项目管理（FR-1）

系统 SHALL 提供投标项目管理：工作台可新建、查看、编辑、删除项目；项目记录名称、招标方、行业、预算金额、投标截止时间与流程状态；状态 SHALL 随流程流转（草稿→已上传→已拆标→已生成→已自检→已导出）。

#### Scenario: 新建与流转

- GIVEN 用户进入投标工作台
- WHEN 用户新建项目并填写名称/招标方/行业/预算/截止时间
- THEN 项目出现在列表中，状态为「草稿」；后续上传/拆标/生成/自检/导出依次推进状态

### Requirement: 规范书上传与文本抽取（FR-2）

系统 SHALL 支持在项目详情页上传 docx/pdf/xlsx/txt 格式规范书（可多个）；SHALL 保存原文件并抽取可检索文本；SHALL 支持下载原文件。上传后 SHALL 将抽取文本同步写入项目级知识库（FR-16）。

#### Scenario: 上传规范书

- GIVEN 项目已创建
- WHEN 用户上传一份 docx 规范书
- THEN 原文件落盘到 `uploads/bid/{project_id}/`，文本被抽取并记录，项目状态变为「已上传」，抽取文本写入项目知识库

### Requirement: 拆标解析（FR-3）

系统 SHALL 支持对已上传规范书触发拆标，输出结构化报告，至少包含：资质要求、业绩要求、技术参数、评分标准、废标条款、应答清单六类；未能识别的章节项 SHALL 标注「未识别」，不得编造。

#### Scenario: 拆标输出

- GIVEN 项目已上传规范书
- WHEN 用户触发拆标
- THEN 系统返回六类结构化报告（JSON），缺项标「未识别」，项目状态变为「已拆标」

### Requirement: 生成投标材料（FR-4）

系统 SHALL 支持基于拆标报告 + 知识库 + 模板生成四类材料：技术方案建议书、招标点对点应答、售前汇报 PPT 大纲、运维实施方案；对拆标中无依据的项 SHALL 标注「待补充材料」，不得编造参数。材料生成 SHALL 通过分步流程（大纲→逐章→组装，FR-19/FR-20/FR-21）调用大模型产出正文初稿；无 LLM 时降级为规则模板并标注「待补充材料」。

#### Scenario: 生成材料

- GIVEN 项目已完成拆标
- WHEN 用户选择材料类型触发生成
- THEN 系统返回生成文本并落盘，含「待补充材料」标注的条目，项目状态变为「已生成」

### Requirement: 合规自检（FR-5）

系统 SHALL 支持对生成材料执行合规自检，输出：未响应项清单、废标红线提示、评分点得分建议三类结果。

#### Scenario: 自检结果

- GIVEN 项目已生成材料
- WHEN 用户触发合规自检
- THEN 系统返回未响应项/红线提示/评分建议，项目状态变为「已自检」

### Requirement: 成果导出（FR-6）

系统 SHALL 支持将生成成果导出为 docx 或 markdown 文件供下载。

#### Scenario: 导出成果

- GIVEN 项目存在生成成果
- WHEN 用户请求导出（fmt=docx 或 md）
- THEN 系统返回对应格式文件下载，项目状态变为「已导出」

### Requirement: 聊天跳转工作台（FR-7）

系统 SHALL 区分 emp-007 的聊天请求：信息类问答（资质要求有哪些、评分标准解读、中标经验咨询）SHALL 在聊天内基于知识库回答；凡涉及上传规范书、拆标、生成应答、合规自检、导出文档的重操作请求，SHALL 引导用户跳转投标工作台 `/bidding` 并说明页面内已支持的操作。

#### Scenario: 重操作跳转

- GIVEN 用户向 emp-007 提出「帮我拆标这份规范书」
- WHEN 对话执行
- THEN emp-007 回复引导语（附 `http://127.0.0.1:9007/bidding` 链接），不在聊天内执行拆标

#### Scenario: 信息类问答

- GIVEN 用户向 emp-007 提问「投标需要哪些资质」
- WHEN 对话执行
- THEN emp-007 基于绑定知识库在聊天内直接回答

### Requirement: 后台管理门户入口（FR-9）

系统 SHALL 在后台管理门户（`/manage`）的「工作成果」菜单页面提供投标工作台入口卡片，点击后在新标签页打开 `/bidding`；该入口 SHALL 与既有业务平台入口并列展示，不干扰既有卡片。

#### Scenario: 后台直达工作台

- GIVEN 管理员打开后台管理门户并进入「工作成果」页面
- WHEN 点击「投标工作台」卡片
- THEN 新标签页打开 `/bidding`，页面可正常完成拆标/生成/自检/导出链路

### Requirement: 多文件分类解析（FR-10）

系统 SHALL 支持上传时为每个文件指定分类（`feasibility/technical/commercial/contract/format/other`，经 `categories` JSON 参数传递）；未指定分类的文件 SHALL 按文件名 + 文本头部关键词自动识别（仅作初值，界面可手动覆盖）。各分类的抽取文本 SHALL 独立落盘于 `extracted/<category>/`；旧版平铺结构（`extracted/<name>.txt`）SHALL 视为 `other` 且可正常拆标。拆标主文本 SHALL 仅合并 `technical/commercial/contract/other` 四类（可研不参与主拆标，避免过时参数污染正式标书）；若主文本为空 SHALL 回退全量合并。合并文本 SHALL 按文件分段携带【来源文件：文件名】标记，LLM 精提炼的 `source` 字段 SHALL 标注「文件名·章节」。项目详情文件列表 SHALL 返回每个文件的分类标签。

#### Scenario: 分类上传与溯源拆标

- GIVEN 客户上传可研文件与技术要求文件并分别标记分类
- WHEN 用户触发拆标
- THEN 可研文本不参与主拆标（其过时参数不进入报告）；拆标条目 source 可溯源到「文件名·章节」

### Requirement: 投标格式规范（FR-11）

系统 SHALL 按统一排版基线渲染 docx 导出：正文宋体小四 12pt、1.5 倍行距、首行缩进约 0.85cm（2 字符）；一级标题黑体三号 16pt 居中、二级黑体四号 14pt、三级黑体小四 12pt；页边距上/下 2.54cm、左/右 3.17cm（A4）；页脚居中页码。SHALL 显式设置中文字体（`w:eastAsia`）避免中文回退；标题统一黑色。SHALL 自动生成封面（项目名称/投标文件/招标方/日期）与静态目录页（基于文档标题行）。

#### Scenario: 排版基线导出

- GIVEN 项目存在生成成果且无格式要求文件
- WHEN 用户导出 docx
- THEN 文档采用默认排版基线（宋体正文/黑体标题/规范页边距/页码/封面/目录）

### Requirement: 格式要求自动提取覆盖（FR-12）

系统 SHALL 在拆标时读取 `format` 分类文本，通过关键词提取字体/字号/行距/页边距/页码规范并写入 `uploads/bid/{pid}/format_spec.json`；docx 渲染时，格式要求命中的项 SHALL 覆盖默认基线，未命中的项 SHALL 使用默认基线。

#### Scenario: 格式要求覆盖基线

- GIVEN 客户上传「格式编制要求」文件（如正文仿宋三号、页边距自定义）
- WHEN 用户导出 docx
- THEN 正文采用仿宋三号等格式要求值，其余未指定项回退默认基线

### Requirement: 投标模板上传（FR-13）

系统 SHALL 支持在投标工作台上传定稿 docx 投标模板（与「规范书上传 / 拆标解析」三列一行同级），仅接受 `.docx` 文件，单模板覆盖（新上传替换旧模板）。模板 SHALL 落盘于 `uploads/bid/{project_id}/template/`，文件名校验防路径穿越。上传后 SHALL 解析模板章节结构（Heading 1/2/3 与带中文序号段落）并返回章节树；项目详情 SHALL 返回模板名、大小与章节树。系统 SHALL 支持删除已上传模板。

#### Scenario: 上传与查看模板

- GIVEN 项目已创建
- WHEN 用户上传定稿 docx 模板
- THEN 模板落盘并解析章节树，项目详情返回模板名/大小/章节树；再次上传同类型模板 SHALL 覆盖旧模板

#### Scenario: 删除模板

- GIVEN 项目已上传模板
- WHEN 用户删除模板
- THEN 模板文件被移除，项目详情不再返回模板信息

### Requirement: 模板化材料生成（FR-14）

系统 SHALL 在生成材料导出 docx 时，若项目存在已上传模板，SHALL 打开模板副本（完整保留原有内容与样式）并按章节标题匹配将生成内容插入模板对应章节；未匹配的生成章节 SHALL 追加文末。章节匹配 SHALL 基于归一化标题（去「第X章 / 一、二、三、/」序号前缀、空白与小写）双向包含判定。无模板的项目导出 docx SHALL 保持既有排版基线渲染（FR-11/12 不受影响）。

#### Scenario: 模板化导出

- GIVEN 项目已上传模板且已生成材料
- WHEN 用户导出 docx
- THEN 导出文档保留模板全部原有内容与样式，生成内容按章节标题匹配插入对应章节

### Requirement: 技术方案演示网页（FR-15）

系统 SHALL 在材料生成中新增类型 `tech_demo`（技术方案演示网页），产出自包含单 HTML 文件（纯 CSS + 内联 SVG，零依赖）。演示网页 SHALL 由拆标报告驱动：KPI 指标卡、带坐标轴与图例的折线图 / 环形图、主机状态表格（状态徽标 + 三档指标）、告警列表，数据取自 `tech_params` 等技术参数；SHALL 展示「技术参数响应清单」（合并 `tech_params` 与规范书技术要求 LLM 提炼结果并去重，关键参数标注 ★；LLM 提炼失败 SHALL 静默降级为规则兜底且不阻塞生成）。演示网页 SHALL 可预览（浏览器直接打开）与下载（fmt=html）。演示网页页脚 SHALL 标注「模拟界面原型，数据由拆标报告驱动」。演示网页 SHALL 优先由 LLM 依据需求分析 PRD 与拆标参数生成（FR-18）；LLM 不可用时降级既有拆标驱动规则版本。功能截图区 SHALL 由「文字占位表格骨架」升级为真实截图插入——组装/导出前 SHALL 通过 playwright 渲染 mockup HTML 并截图（全页 + 分区），md 导出以相对路径引用图片，docx 导出以 `add_picture` 真插入 2~3 张；浏览器不可用或截图失败 SHALL 降级为文字占位并记录 warn，不阻断导出。

#### Scenario: 生成演示网页

- GIVEN 项目已完成拆标
- WHEN 用户选择「技术方案演示网页」触发生成
- THEN 系统产出 `.html` 自包含成果，含 KPI/图表（坐标轴图例）/表格/告警与「技术参数响应清单」，数据来自拆标报告

#### Scenario: 预览与下载演示网页

- GIVEN 项目存在 tech_demo 成果
- WHEN 用户点击预览或下载 html
- THEN 预览在新标签页打开页面；下载返回 text/html 文件

#### Scenario: 技术方案功能截图区

- GIVEN 项目生成技术方案建议书并导出 docx
- WHEN 导出完成
- THEN 文档「技术方案要点」后出现功能截图区 Word 表格骨架（功能说明 + 规范引用占位）

### Requirement: 项目资料入库（FR-16）

系统 SHALL 在规范书上传时保留原文件（uploads/bid/{pid}/）并同步将抽取文本写入项目级知识库（kb id = `bid-project-{pid}`，幂等创建/重建）；拆标报告生成后 SHALL 以结构化 Markdown 写入同一项目库；上传模板 SHALL 将其章节结构文本写入项目库。生成/逐章检索范围 SHALL 为项目库 ∪ 预置 5 类投标库。

#### Scenario: 上传即入库

- GIVEN 项目已创建
- WHEN 用户上传一份规范书
- THEN 原文件保留且文本写入 bid-project-{pid}，search_knowledge 可检索到该项目内容

### Requirement: 需求分析（FR-17）

系统 SHALL 支持对项目触发需求分析：LLM 基于上传材料整理为结构化 PRD（用户角色、功能点清单、页面清单、交互说明、验收口径），以开发可读语言输出并落库。LLM 不可用时 SHALL 降级返回拆标报告摘要结构。未完成拆标时触发需求分析 SHALL 拒绝（400）。

#### Scenario: 需求转开发语言

- GIVEN 项目已上传规范书并完成拆标
- WHEN 用户触发需求分析
- THEN 返回结构化 PRD（roles/features/pages/interactions/acceptance），项目状态更新

### Requirement: 假页面生成（FR-18）

系统 SHALL 支持基于 PRD 与拆标技术参数生成假页面：LLM 产出 SHALL 为完整自包含 HTML（侧边导航 + 顶栏 + Dashboard KPI 卡 + 至少 2 个内联 SVG 图表（折线/环形）+ 表格 + 状态徽标，零外部依赖），提示词 SHALL 给出色板与高质量锚示例；LLM 失败仍降级既有规则版本，`source: "llm"/"rule"` 标记保留。假页面 SHALL 可预览与下载。

#### Scenario: 生成假页面

- GIVEN 项目已完成需求分析
- WHEN 用户触发生成假页面
- THEN 产出可预览 HTML，数据来自 PRD 与拆标报告，页脚标注「模拟界面原型」

### Requirement: 大纲与逐章生成（FR-19）

系统 SHALL 支持生成章节大纲（LLM 基于模板章节树+拆标报告）；SHALL 支持逐章生成：单章输入=章节标题+规范要求片段+项目知识库 RAG 片段+已确认章节摘要，独立一次 LLM 调用；每章结果落盘 chapters/{index}.md；单章失败 SHALL 标记「待补充」不中断后续章节。

#### Scenario: 逐章生成

- GIVEN 大纲已生成且当前章节未生成
- WHEN 用户请求生成本章
- THEN 返回本章草稿并落盘，可进入下一章

### Requirement: 左右对照逐章确认（FR-20）

系统 SHALL 提供左右对照编辑视图：左栏展示本章对应规范书要求（拆标卡片/原文片段），右栏展示 AI 草稿并支持编辑；SHALL 支持「确认本章」与「重新生成本章」；仅已确认章节参与最终组装。逐章草稿生成 SHALL 可被一键起草编排自动触发（全量章节循环生成，单章失败标「待补充」不中断）；人工复核确认逻辑保持不变，确认后由编排或人工触发组装。

#### Scenario: 逐章确认

- GIVEN 当前章节草稿已生成
- WHEN 用户点击确认本章
- THEN 本章锁定为定稿并进入下一章；重新生成则丢弃旧草稿重新调用 LLM

### Requirement: 流程进度与组装（FR-21）

系统 SHALL 将投标材料产出组织为 6 步 SOP（上传→拆标→需求→假页面→逐章→组装），前端 SHALL 提供步骤进度条与执行中 loading 遮罩；SHALL 支持在全部章节确认后组装为最终文档（md/docx），落盘 outputs/ 并进入成果列表。组装 SHALL 可被编排自动触发（auto_confirm=True）或人工确认全部章节后触发；组装后 SHALL 自动执行合规自检（check_compliance）并将结果随组装返回；组装产物 SHALL 包含界面截图（见 FR-15 修改）。

#### Scenario: 组装导出

- GIVEN 全部章节已确认
- WHEN 用户触发组装
- THEN 合成最终文档落盘并出现在成果列表，可导出 docx/md

## 非功能需求

- NFR-1：规范书解析 SHALL 支持 500 页级大文档分块处理；文本抽取 SHALL 覆盖 docx/pdf/xlsx/txt 四种格式。

## 测试标准

- TC-1：覆盖 FR-1~FR-23 的用例位于 `tests/test_bid.py`，每条用例标注规格编号（如 `# NO-009 FR-3`）。
- TC-2：拆标无 LLM（网络不可用）时，规则粗筛 SHALL 仍产出六类章节骨架，缺项标「未识别」。
- TC-3：FR-10 分类解析 SHALL 验证：分类上传落盘、自动识别、主拆标可研隔离与来源头（test_bid_upload_with_category / test_bid_auto_category / test_bid_parse_category_priority）。
- TC-4：FR-11/FR-12 格式规范 SHALL 验证：格式关键词提取、docx 导出排版基线（test_bid_extract_format_spec / test_bid_export_docx_styled）。
- TC-5：FR-13/14/15 SHALL 验证：模板上传/章节树/覆盖/删除、模板化导出（模板内容保留 + 生成内容插入）、演示网页生成与 html 导出、docx 功能截图区表格骨架（test_bid_template_* / test_bid_demo_*）。
- TC-6：FR-16 项目入库 SHALL 验证：上传后项目知识库创建、拆标报告入库、检索命中项目内容（test_bid_project_kb_write_on_upload）。
- TC-7：FR-17 需求分析 SHALL 验证：PRD 结构完整并落库、未拆标触发被拒（test_bid_requirements_prd / test_bid_requirements_without_parse_rejected）。
- TC-8：FR-18 假页面 SHALL 验证：mockup 落盘 outputs/、含「模拟界面原型」与「技术参数响应清单」、进入成果列表（test_bid_mockup_generate）。
- TC-9：FR-19/20 大纲逐章 SHALL 验证：大纲 ≥8 章、逐章生成落库（source=llm/rule）、无大纲被拒、确认定稿与重生成、无草稿不可确认（test_bid_outline_and_chapter / test_bid_chapter_confirm）。
- TC-10：FR-21 组装 SHALL 验证：全章节确认后组装产物进入成果列表、md 可导出、无确认章节被拒（test_bid_assemble_document / test_bid_assemble_without_confirmed）。
