# 设计：投标模板上传 + 模板化材料生成 + 技术方案演示网页

## 磁盘结构（新增/兼容）

```
uploads/bid/{pid}/
├── {原规范书文件}               # 不变
├── extracted/<category>/...     # 不变
├── format_spec.json             # 不变
├── template/
│   └── {name}.docx              # 新增：投标模板（单模板覆盖）
└── outputs/{doc_id}.{md|html|docx}  # tech_demo 产出 .html
```

## 模块改动

### app/bidding/bid_engine.py

- 常量：`DOC_TYPES` 新增 `tech_demo = "技术方案演示网页"`；`DEMO_STYLE_CSS`（高保真深色科技风骨架样式，取自 demo-preview.html 的 `:root` 变量与组件样式）。
- 新增 `parse_template_structure(template_path)`：读取 docx Heading 1/2/3 与带中文序号（"一、二、…"）段落，产出 `[{level, title}]` 章节树。
- 新增 `_norm_title(s)`：去"第X章/一、二、三、/"序号前缀与空白、小写，用于双向包含匹配。
- 新增 `save_bid_template(project_id, file)` / `delete_bid_template(project_id)` / `load_bid_template(project_id)`：保存（`_safe_name` 防穿越，仅 .docx）/删除/读取元信息。
- 新增 `_render_docx_with_template(md_path, out_path, proj, template_path, spec)`：打开模板副本，解析生成 md 章节（`## 标题` + 内容块），`_norm_title` 归一化后双向包含匹配模板标题，匹配→在模板标题段落后插入，未匹配→追加文末；插入段落复用模板 Normal/Heading 样式；最终以模板副本为导出结果。
- 改造 `generate_document`：`tech_demo` 分支调用 `_build_demo_html` 落盘 `.html`（跳过 md）。
- 新增 `_demo_features(report, technical_text)`：功能清单两来源合并去重——`tech_params`（item/value/acceptance/source，is_key 标 ★）+ 规范书 technical 原文 LLM 提炼（`_call_llm_json` + `_record_llm`，失败静默降级规则兜底）。
- 新增 `_build_demo_html(proj, features, params)`：以 `static/demo-preview.html` 为蓝本做数据驱动模板化——KPI 卡、折线/环形图图例与数值、主机表格、告警列表全部由报告数据填充；SVG 坐标固定骨架 + 数据换算；页脚标注"模拟界面原型，数据由拆标报告驱动"。
- 改造 `export_document`：`fmt=html` 直接返回文件；docx 导出 `tech_proposal` 时在"技术方案要点"后插入 Word 表格骨架（灰色标题栏 + 占位单元格 + 功能说明 + 规范引用）。

### app/bidding/routes_bidding.py

- 新增 `POST /api/bid/projects/{pid}/template`（UploadFile，仅 .docx）：保存模板并返回章节树。
- 新增 `DELETE /api/bid/projects/{pid}/template`：删除模板。
- `GET /api/bid/projects/{pid}`：返回 `template` 字段（name/size/structure）。
- `export_document`：`fmt=html` 时媒体类型 `text/html`。

### static/bidding.html

- 上传行 `grid-2` 改 `grid-3`：规范书上传 / 拆标解析 / 投标模板上传三卡片一行；模板卡片含独立 file input（`accept=".docx"`）、当前模板名 + 章节树 + 删除按钮。
- 生成区新增"技术方案演示网页"按钮（POST generate，type=tech_demo）。
- 成果列表对 `tech_demo` 显示"预览"（新窗口打开 `/static/outputs/...html`）与"下载 html"。

### static/demo-preview.html（新增）

- 高保真演示原型，独立可预览；`_build_demo_html` 的蓝本。深色科技风运维大屏：浏览器窗口壳（红黄绿圆点 + 地址栏）、左侧导航（logo/菜单/告警角标）、顶栏（面包屑/标题/搜索/通知/头像）、4 张 KPI 卡、SVG 折线图（双系列 + 坐标轴 + 图例 + tooltip）、SVG 环形图（4 段占比 + 图例 + 中心文案）、主机状态表格（三档进度条 + 徽标）、告警列表（时间戳 + 级别 + 阈值文案 + 处置建议）。

### tests/test_bid.py

- FR-13：模板上传/章节树解析/删除/单模板覆盖。
- FR-14：有模板导出 docx 章节匹配插入（zip 解包断言模板段落保留 + 生成内容插入）。
- FR-15：tech_demo 生成产出 .html 且含 KPI/图表/表格/告警区块与报告数据。

## 兼容性

- 无模板项目导出 docx：走既有 `_render_docx` 基线，行为与 FR-11/12 完全一致。
- 四类既有材料 md 生成逻辑不动；仅新增 tech_demo 类型与导出扩展点。
- 旧项目无 `template/` 目录：`load_bid_template` 返回 None，生成/导出平滑降级。
- 演示网页数据由拆标报告驱动，LLM 提炼失败静默降级，不阻塞生成。
