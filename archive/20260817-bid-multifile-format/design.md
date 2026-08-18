# 设计：多文件分类解析 + 格式统一约束

## 文件分类与拆标优先级

| key | 中文名 | 参与主拆标 | 说明 |
|-----|--------|-----------|------|
| feasibility | 可研文件 | 否 | 仅兜底（主文本为空时全量合并） |
| technical | 技术要求 | 是 | 技术参数主体 |
| commercial | 商务要求 | 是 | 商务条款 |
| contract | 合同文稿 | 是 | 合同条款 |
| format | 格式要求 | 否（单独提取） | 生成排版规范 |
| other | 其他 | 是 | 兜底 |

## 磁盘结构（新增/兼容）

```
uploads/bid/{pid}/
├── {原文件}                    # 原样保存（不变）
├── extracted/
│   ├── {category}/{name}.txt   # 新增：分类子目录
│   └── {name}.txt              # 兼容：旧版平铺（视为 other）
└── format_spec.json            # 新增：格式规范（拆标时生成）
```

## 模块改动

### app/bidding/bid_engine.py
- 新增常量：`BID_FILE_CATEGORIES`、`MAIN_PARSE_CATEGORIES`、`DOCX_STYLE_DEFAULTS`、`FONT_SIZE_MAP`。
- 新增 `auto_category(name, head_text)`：文件名关键词 → 内容兜底（保守关键词）。
- 改造 `_read_extracted_text(project_id, categories=None)`：支持分类子目录 + 平铺兼容 + 【来源文件】头。
- 新增 `extract_format_spec(text)` / `save_format_spec` / `load_format_spec` / `_merge_format_spec`。
- 改造 `parse_bid_document`：主拆标分类合并 + format 单独提取落盘 + 响应附加 `format_spec`（不写入 DB，保持六类契约）。
- 改造 `export_document` docx 分支 → `_render_docx(md_path, out_path, proj, spec)`；新增 `_style_heading` / `_add_cover` / `_add_toc` / `_add_page_number` / `_add_runs`。
- `LLM_JSON_SCHEMA_HINT` 增加 source 溯源要求。

### app/bidding/routes_bidding.py
- upload 接口增加 `categories: str = Form("")`；抽取文本按分类落盘；`saved` 返回 dict（name + category）。
- `_list_files` 返回 `category` 字段（反查 extracted 分类子目录，缺失则自动识别）。

### static/bidding.html
- 上传面板：选文件后预览每文件分类下拉（默认前端轻量自动识别），上传时序列化 categories。
- 文件列表：显示分类标签。
- 拆标结果：顶部展示「投标格式规范」卡片（parse 响应附带的 format_spec）。

### tests/test_bid.py
- FR-10：分类上传落盘 / 自动识别 / 拆标优先级与 source 头。
- FR-11/12：格式关键词提取 / docx 导出排版基线（zip 解包断言字体与页边距）。

## 兼容性

- 旧平铺 extracted 数据：`_read_extracted_text` 平铺文件视为 other，主拆标类别含 other，可正常拆标。
- 旧项目无 format_spec.json：`_merge_format_spec({})` 返回默认基线，导出行为平滑升级。
- 拆标报告六类结构不变；parse 响应仅新增 `format_spec` 附加键（`>=` 契约不受影响）。
