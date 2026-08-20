# Delta: 投标工作台 SOP 化分步编写流程（NO-009）

> 变更编号：`20260817-bid-writeflow`
> 状态：草稿 | 合并目标：`specs/009-bid-expert/spec.md`

## ADDED

### Requirement: 项目资料入库（FR-16）

系统 SHALL 在规范书上传时保留原文件（uploads/bid/{pid}/）并同步将抽取文本写入项目级
知识库（kb id = `bid-project-{pid}`，幂等创建/重建）；拆标报告生成后 SHALL 以结构化
Markdown 写入同一项目库；上传模板 SHALL 将其章节结构文本写入项目库。生成/逐章检索
范围 SHALL 为项目库 ∪ 预置 5 类投标库。

#### Scenario: 上传即入库

- GIVEN 项目已创建
- WHEN 用户上传一份规范书
- THEN 原文件保留且文本写入 bid-project-{pid}，search_knowledge 可检索到该项目内容

### Requirement: 需求分析（FR-17）

系统 SHALL 支持对项目触发需求分析：LLM 基于上传材料整理为结构化 PRD（用户角色、
功能点清单、页面清单、交互说明、验收口径），以开发可读语言输出并落库。
LLM 不可用时 SHALL 降级返回拆标报告摘要结构。

#### Scenario: 需求转开发语言

- GIVEN 项目已上传规范书并完成拆标
- WHEN 用户触发需求分析
- THEN 返回结构化 PRD（roles/features/pages/interactions），项目状态更新

### Requirement: 假页面生成（FR-18）

系统 SHALL 支持基于 PRD 与拆标技术参数生成假页面：LLM 产出单 HTML（纯 CSS+内联 SVG，
零依赖），含页面导航、各功能页面骨架、KPI 卡、技术参数响应清单（关键项标 ★）；
生成失败 SHALL 降级为既有 _build_demo_html 规则版本。假页面 SHALL 可预览与下载。

#### Scenario: 生成假页面

- GIVEN 项目已完成需求分析
- WHEN 用户触发生成假页面
- THEN 产出可预览 HTML，数据来自 PRD 与拆标报告，页脚标注「模拟界面原型」

### Requirement: 大纲与逐章生成（FR-19）

系统 SHALL 支持生成章节大纲（LLM 基于模板章节树+拆标报告）；SHALL 支持逐章生成：
单章输入=章节标题+规范要求片段+项目知识库 RAG 片段+已确认章节摘要，独立一次 LLM 调用；
每章结果落盘 chapters/{index}.md；单章失败 SHALL 标记「待补充」不中断后续章节。

#### Scenario: 逐章生成

- GIVEN 大纲已生成且当前章节未生成
- WHEN 用户请求生成本章
- THEN 返回本章草稿并落盘，可进入下一章

### Requirement: 左右对照逐章确认（FR-20）

系统 SHALL 提供左右对照编辑视图：左栏展示本章对应规范书要求（拆标卡片/原文片段），
右栏展示 AI 草稿并支持编辑；SHALL 支持「确认本章」与「重新生成本章」；仅已确认章节
参与最终组装。

#### Scenario: 逐章确认

- GIVEN 当前章节草稿已生成
- WHEN 用户点击确认本章
- THEN 本章锁定为定稿并进入下一章；重新生成则丢弃旧草稿重新调用 LLM

### Requirement: 流程进度与组装（FR-21）

系统 SHALL 将投标材料产出组织为 6 步 SOP（上传→拆标→需求→假页面→逐章→组装），
前端 SHALL 提供步骤进度条与执行中 loading 遮罩；SHALL 支持在全部章节确认后组装为
最终文档（md/docx），落盘 outputs/ 并进入成果列表。

#### Scenario: 组装导出

- GIVEN 全部章节已确认
- WHEN 用户触发组装
- THEN 合成最终文档落盘并出现在成果列表，可导出 docx/md

## MODIFIED

### Requirement: 规范书上传与文本抽取（FR-2）

MODIFIED：在「保存原文件并抽取可检索文本」基础上，SHALL 增加「抽取文本写入项目级
知识库 bid-project-{pid}」；原文件下载能力保持不变。

### Requirement: 生成投标材料（FR-4）

MODIFIED：材料生成 SHALL 通过分步流程（大纲→逐章→组装）调用大模型产出正文初稿；
无 LLM 时降级为规则模板并标注「待补充材料」，不编造参数。

### Requirement: 技术方案演示网页（FR-15）

MODIFIED：演示网页 SHALL 优先由 LLM 依据需求分析 PRD 与拆标参数生成（FR-18）；
LLM 不可用时降级既有拆标驱动规则版本。
