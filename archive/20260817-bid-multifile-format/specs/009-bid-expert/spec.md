# NO-009 bid-expert — delta 增量规格（2026-08-17）

> 本文件为变更增量（ADDED），归档后合并入 `specs/009-bid-expert/spec.md`。

## ADDED

### FR-10 多文件分类解析

- SHALL：上传接口接受可选 `categories` 参数（JSON 映射「文件名 → 分类」），分类集合固定为 `feasibility / technical / commercial / contract / format / other`。
- SHALL：未指定分类的文件按文件名 + 文本头部关键词自动识别分类（自动识别仅作初值，用户可在界面手动覆盖）。
- SHALL：各分类的抽取文本独立落盘于 `extracted/<category>/`；旧版平铺结构（`extracted/<name>.txt`）视为 `other` 且必须可正常拆标。
- SHALL：拆标主文本仅合并 `technical`、`commercial`、`contract`、`other` 四类（可研不参与主拆标，避免过时参数污染正式标书）；若主文本为空则回退全量合并（兼容仅可研场景）。
- SHALL：合并文本按文件分段并携带【来源文件：文件名】标记；LLM 精提炼提示词要求 `source` 字段标注「文件名·章节」。
- SHALL：项目详情文件列表返回每个文件的分类标签。

### FR-11 投标格式规范（docx 排版基线）

- SHALL：docx 导出按默认排版基线渲染：正文宋体小四 12pt、1.5 倍行距、首行缩进约 0.85cm（2 字符）；一级标题黑体三号 16pt 居中，二级黑体四号 14pt，三级黑体小四 12pt；页边距上/下 2.54cm、左/右 3.17cm（A4）；页脚居中页码。
- SHALL：docx 导出自动生成封面（项目名称 / 投标文件 / 招标方 / 日期）与静态目录页（基于文档标题行）。
- SHALL：显式设置中文字体（`w:eastAsia`），避免中文回退为等线/Calibri。
- SHALL：标题样式去除默认蓝色，统一为黑色。

### FR-12 格式要求自动提取覆盖

- SHALL：拆标时读取 `format` 分类文本，通过关键词提取字体 / 字号 / 行距 / 页边距 / 页码规范，写入 `uploads/bid/{pid}/format_spec.json`。
- SHALL：docx 渲染时，格式要求命中的项覆盖默认基线；未命中的项使用默认基线。
