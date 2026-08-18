# 提案：投标智能起草全流程编排（一键生成 + 横向流程视图 + 截图与演示质量升级）

> 变更编号：`20260817-bid-autoflow`
> 作者：AI 助手 | 日期：2026-08-17 | 状态：草稿

## 背景与问题

现有投标工作台为「分步手动触发」模式：上传/拆标/需求/假页面/逐章/组装每一步需用户
点击，纵向卡片堆叠，无整体编排；逐章生成后仍需人工逐章确认才能组装；假页面由
LLM 输出 JSON 骨架再套规则模板，样式简陋不专业；方案 docx 导出中功能截图区仅有
文字占位，无真实界面截图。

## 目标

1. 一键智能起草：一次点击自动跑完「拆标→需求→假页面→大纲→逐章」，默认停在人工复核
2. 流程视图横向化：顶部上传卡片 + 中间「开始生成」主按钮 + 横向步骤条自动滑动
3. 演示页面专业度提升：LLM 直出完整 HTML（侧边导航 + 顶栏 + 内联 SVG 图表）
4. 方案真实截图：playwright 渲染 mockup 截图，md 引用、docx 真插入图片

## 变更范围

### In Scope

- 新增 `run_bid_pipeline(pid, auto_confirm=False)` 编排函数与内存进度表
- 新增 `POST /api/bid/projects/{pid}/pipeline/run`、`GET .../pipeline/status`
- 新增 playwright 截图模块 `app/bidding/screenshot.py`（懒加载单例，无浏览器降级占位）
- 组装时 md 引用截图、docx `_add_demo_shot_table` 改为 `add_picture` 真插入
- mockup 提示词升级：LLM 直出完整 HTML，规则版仅兜底
- 前端布局重构：两个上传卡片 → 「开始生成」主按钮 → 横向 6 步步骤条 + 面板横向滑动
- 移除「快捷生成」卡片；「合规自检」并入组装步面板
- 新增测试：pipeline 编排顺序/停复核/全自动/无文件拒绝/截图插入

### Out of Scope

- 服务端定时任务与多人协作
- 截图服务的自托管浏览器池（沿用懒加载单例）

## 接口与数据契约

### 新增接口

- `POST /api/bid/projects/{pid}/pipeline/run`  body: `{auto_confirm?: bool}`
  → 202 `{status: "running"}`；完成后 `{status: "awaiting_review"|"done", doc_id?, check?}`
- `GET /api/bid/projects/{pid}/pipeline/status`
  → 200 `{stage: "parse"|"requirements"|"mockup"|"outline"|"chapters"|"shots"|"assemble"|"review"|"done", stage_index, total, message, done: bool}`

### 流程编排（auto_confirm=False）

```
校验已上传规范书 → ①拆标 → ②需求分析 → ③假页面 → ④大纲 → ⑤逐章全量草稿
→ ⑥playwright 截图 → status=awaiting_review（等人工复核/确认）
（auto_confirm=True 时跳过人工，直接组装 → 自检 → 导出 docx[含截图]）
```

## 涉及规格条目

- ADDED: NO-009 FR-22（一键智能起草与进度上报）、FR-23（横向流程视图）
- MODIFIED: NO-009 FR-15（docx 截图真插入）、FR-18（LLM 直出 HTML）、
            FR-20（复核与确认入编排）、FR-21（组装并入编排 + 合规自检）

## 验收标准

- [ ] 一键生成：上传规范书后点「开始生成」，自动完成拆标→需求→假页面→大纲→逐章并停在复核
- [ ] 前端步骤条随进度自动横向滑动，面板横向布局可滚动
- [ ] mockup HTML 由 LLM 直出（含侧边导航/顶栏/内联 SVG 图表），失败降级规则版
- [ ] 组装后 md/docx 含真实界面截图（无浏览器时降级文字占位且不阻断）
- [ ] 逐章面板保留左右对照人工复核，确认后进入组装
- [ ] 全自动模式（auto_confirm=true）完成组装+自检+导出全链路
- [ ] 未上传规范书触发 pipeline 返回 400

## 风险与兼容性

- playwright 首次截图需下载 chromium，失败/超时降级文字占位（不阻断流程）
- 既有 /generate、/requirements、/mockup 等单步接口保持兼容
- pipeline 进度表为内存态，服务重启后重建（按 pid 幂等覆盖）
- 移除「快捷生成」卡片不影响后端 /generate 接口（保留兼容）
