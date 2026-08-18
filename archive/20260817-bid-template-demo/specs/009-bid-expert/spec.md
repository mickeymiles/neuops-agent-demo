# NO-009 bid-expert — delta 增量规格（2026-08-17）

> 本文件为变更增量（ADDED），归档后合并入 `specs/009-bid-expert/spec.md`。

## ADDED

### FR-13 投标模板上传

- SHALL：投标工作台 SHALL 支持上传定稿 docx 模板（与"规范书上传 / 拆标解析"三列一行同级），仅接受 `.docx` 文件，单模板覆盖（新上传替换旧模板）。
- SHALL：模板 SHALL 落盘于 `uploads/bid/{pid}/template/`，文件名校验防路径穿越。
- SHALL：上传后 SHALL 解析模板章节结构（Heading 1/2/3 与带中文序号段落）并返回章节树；项目详情 SHALL 返回模板名、大小与章节树。
- SHALL：SHALL 支持删除已上传模板。

### FR-14 模板化材料生成

- SHALL：生成材料导出 docx 时，若项目存在已上传模板，SHALL 打开模板副本（完整保留原有内容与样式）并按章节标题匹配将生成内容插入对应章节；未匹配的生成章节 SHALL 追加文末。
- SHALL：章节匹配 SHALL 基于归一化标题（去"第X章 / 一、二、三、/"序号前缀、空白与小写）双向包含判定。
- SHALL：无模板的项目导出 docx SHALL 保持既有排版基线渲染（FR-11/12 不受影响）。

### FR-15 技术方案演示网页

- SHALL：生成材料 SHALL 新增类型 `tech_demo`（技术方案演示网页），产出自包含单 HTML 文件（纯 CSS + 内联 SVG，零依赖）。
- SHALL：演示网页 SHALL 由拆标报告驱动：KPI 指标卡、带坐标轴与图例的折线图 / 环形图、主机状态表格（状态徽标 + 三档指标）、告警列表，数据取自 `tech_params` 等技术参数。
- SHALL：功能清单 SHALL 合并拆标报告 `tech_params` 与规范书技术要求 LLM 提炼结果并去重，关键参数标注 ★；LLM 提炼失败 SHALL 静默降级（规则兜底）且不阻塞生成。
- SHALL：演示网页 SHALL 可预览（浏览器直接打开）与下载（fmt=html）。
- SHALL：导出 docx 技术方案 SHALL 在"技术方案要点"后插入 Word 表格骨架（功能说明 + 规范引用）作为功能截图区占位。
- SHALL：演示网页页脚 SHALL 标注"模拟界面原型，数据由拆标报告驱动"。
