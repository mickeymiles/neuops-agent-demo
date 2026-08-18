# Delta: 投标智能起草全流程编排（NO-009）

> 变更编号：`20260817-bid-autoflow`
> 状态：草稿 | 合并目标：`specs/009-bid-expert/spec.md`

## ADDED

### Requirement: 一键智能起草（FR-22）

系统 SHALL 提供一键智能起草编排：一次触发按序自动执行「拆标 → 需求分析 → 假页面 →
大纲 → 逐章全量草稿 → 界面截图」，默认停在人工复核态；人工复核完成后 SHALL 可触发
组装与合规自检。编排 SHALL 提供内存进度表（`{pid: stage}`）供前端轮询，进度阶段依次为
parse/requirements/mockup/outline/chapters/shots/assemble/review/done；任一步骤失败
SHALL 降级不中断（沿用既有降级规则）。编排 SHALL 支持全自动模式（`auto_confirm=True`），
跳过人工复核直接完成组装、合规自检并导出 docx（含截图）。未上传规范书触发编排 SHALL
拒绝（400）。

#### Scenario: 一键智能起草

- GIVEN 项目已上传规范书
- WHEN 用户点击「开始生成」触发编排
- THEN 系统自动完成拆标→需求→假页面→大纲→逐章→截图，进度逐阶段上报，最后停在人工复核

#### Scenario: 全自动模式

- GIVEN 项目已上传规范书且调用方传 auto_confirm=True
- WHEN 编排执行
- THEN 系统跳过人工复核，自动完成组装、合规自检并导出 docx（含界面截图）

#### Scenario: 未上传文件被拒

- GIVEN 项目未上传规范书
- WHEN 用户触发编排
- THEN 系统返回 400 并提示先上传规范书

### Requirement: 横向流程视图（FR-23）

系统 SHALL 提供横向 6 步流程视图：顶部并排两个上传卡片（规范书 / 投标模板），中部
「开始生成」主按钮，下方横向步骤条（上传→拆标→需求→假页面→逐章→组装）与横向滑动
内容面板；步骤完成 SHALL 自动平滑滑动到当前步骤。逐章步骤 SHALL 保留左右对照人工复核
编辑器（左=规范要求，右=AI 草稿）。「合规自检」按钮 SHALL 保留在组装步骤面板。

#### Scenario: 横向滑动

- GIVEN 用户触发一键起草
- WHEN 某步骤完成
- THEN 步骤条与内容面板自动横向滑动到该步骤，当前步骤高亮

## MODIFIED

### Requirement: 技术方案演示网页（FR-15）

MODIFIED：功能截图区 SHALL 由「文字占位表格骨架」升级为真实截图插入——组装/导出前
SHALL 通过 playwright 渲染 mockup HTML 并截图（全页 + 分区），md 导出以相对路径引用
图片，docx 导出以 `add_picture` 真插入 2~3 张；浏览器不可用或截图失败 SHALL 降级为
文字占位并记录 warn，不阻断导出。

### Requirement: 假页面生成（FR-18）

MODIFIED：LLM 产出 SHALL 为完整自包含 HTML（侧边导航 + 顶栏 + Dashboard KPI 卡 +
至少 2 个内联 SVG 图表（折线/环形）+ 表格 + 状态徽标，零外部依赖），提示词 SHALL
给出色板与高质量锚示例；LLM 失败仍降级既有规则版本，`source: "llm"/"rule"` 标记保留。

### Requirement: 左右对照逐章确认（FR-20）

MODIFIED：逐章草稿生成 SHALL 可被一键起草编排自动触发（全量章节循环生成，单章失败
标「待补充」不中断）；人工复核确认逻辑保持不变，确认后由编排或人工触发组装。

### Requirement: 流程进度与组装（FR-21）

MODIFIED：组装 SHALL 可被编排自动触发（auto_confirm=True）或人工确认全部章节后触发；
组装后 SHALL 自动执行合规自检（check_compliance）并将结果随组装返回；组装产物
SHALL 包含界面截图（见 FR-15 修改）。
