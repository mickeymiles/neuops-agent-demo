# 设计：投标智能起草全流程编排

> 变更编号：`20260817-bid-autoflow`

## 1. 后端编排（FR-22）

### 1.1 进度表（内存态）

```python
# bid_engine.py 模块级
PIPELINE_STAGES = ["parse", "requirements", "mockup", "outline", "chapters", "shots", "assemble", "review"]
_PIPELINE_PROGRESS: dict[int, dict] = {}  # {pid: {stage, index, total, message, done, updated_at}}

def _set_progress(pid, stage, index=0, total=len(PIPELINE_STAGES), message="", done=False):
    _PIPELINE_PROGRESS[pid] = {"stage": stage, "index": index, "total": total,
                               "message": message, "done": done}

def get_pipeline_status(pid) -> dict:
    return _PIPELINE_PROGRESS.get(pid, {"stage": "idle", "index": 0, "total": len(PIPELINE_STAGES),
                                        "message": "未开始", "done": False})
```

### 1.2 编排函数

```python
def run_bid_pipeline(project_id: int, auto_confirm: bool = False) -> dict:
    """一键智能起草：拆标→需求→假页面→大纲→逐章→截图；默认停复核，auto_confirm 全自动。"""
    proj = db.bid_get_project(project_id)
    if not proj or not proj.get("uploaded_files"):      # 校验已上传规范书
        raise HTTPException(400, "请先上传规范书")
    _set_progress(project_id, "parse", 0, message="开始拆标")
    if not proj.get("parse_report"):
        parse_document(project_id)                       # ① 拆标
    _set_progress(project_id, "requirements", 1, message="需求分析中")
    requirements_analysis(project_id)                    # ② 需求分析（幂等/降级）
    _set_progress(project_id, "mockup", 2, message="生成演示页面")
    generate_mockup(project_id)                          # ③ 假页面
    _set_progress(project_id, "outline", 3, message="生成章节大纲")
    generate_outline(project_id)                         # ④ 大纲（无模板也可）
    _set_progress(project_id, "chapters", 4, message="逐章编写中")
    chapters = db.bid_get_chapters(project_id) or []
    for i, c in enumerate(chapters):                     # ⑤ 逐章全量草稿
        if not c.get("content"):
            try:
                generate_chapter(project_id, c["index"], force=False)
            except Exception:
                continue                                 # 单章失败降级，不中断
    _set_progress(project_id, "shots", 5, message="生成界面截图")
    try:
        shot_mockup(project_id)                          # ⑥ playwright 截图（失败降级）
    except Exception as e:
        logger.warning("pipeline screenshot failed: %s", e)
    if auto_confirm:                                     # 全自动
        _set_progress(project_id, "assemble", 6, message="组装与自检中")
        doc = assemble_document(project_id, confirm_all=True)
        check_compliance(project_id)
        _set_progress(project_id, "review", 7, message="已完成", done=True)
        return {"status": "done", "doc_id": doc.get("id"), "doc_type": doc.get("doc_type")}
    _set_progress(project_id, "review", 6, message="等待人工复核", done=True)
    return {"status": "awaiting_review"}
```

### 1.3 路由

```python
@router.post("/projects/{pid}/pipeline/run")   # body: {auto_confirm?: bool}
@router.get("/projects/{pid}/pipeline/status")
```

pipeline 为同步执行（单项目串行）；`auto_confirm` 走组装+自检。进度由前端轮询
`/pipeline/status` 驱动步骤条滑动。

## 2. 截图模块（FR-15 修改）

新文件 `app/bidding/screenshot.py`：

```python
import functools, threading, logging, time
from pathlib import Path

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_browser = None
_last_used = 0.0
TTL = 300  # 5 分钟无操作关闭浏览器

def _get_browser():
    """懒加载 playwright chromium 单例；失败抛异常由调用方降级。"""
    global _browser, _last_used
    with _lock:
        if _browser is None or time.time() - _last_used > TTL:
            if _browser:
                try: _browser.close()
                except Exception: pass
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            _browser = pw.chromium.launch(args=["--no-sandbox"])
            _browser.__pw = pw
        _last_used = time.time()
        return _browser

def shot_mockup(project_id: int) -> list[str]:
    """渲染 outputs/mockup.html → 全页 + 分区截图到 outputs/mockup-shots/。返回相对路径列表。"""
    html_path = BID_OUTPUT_DIR / str(project_id) / "mockup.html"
    if not html_path.exists():
        return []
    shots_dir = BID_OUTPUT_DIR / str(project_id) / "mockup-shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    page = _get_browser().new_page(viewport={"width": 1440, "height": 900})
    try:
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(600)
        page.screenshot(path=str(shots_dir / "p1-full.png"))
        for i, sec in enumerate(page.query_selector_all("section"), start=2):
            try:
                sec.screenshot(path=str(shots_dir / f"p{i}.png"))
            except Exception:
                continue
    finally:
        page.close()
    return [f"mockup-shots/p{i}.png" for i in range(1, len(list(shots_dir.glob("*.png"))) + 1)]
```

组装插入（`assemble_document` / `export_document`）：
- md：替换「功能截图区」文本为 `![](mockup-shots/p1-full.png)`
- docx：`_add_demo_shot_table` 改 `add_picture()` 真插入前 2~3 张；无图降级文字占位

## 3. mockup 提示词升级（FR-18 修改）

`_llm_mockup_html` 提示词改为：

```
你是资深前端原型设计师。请为{项目}投标演示网页设计完整的单 HTML 原型，必须满足：
- 单一自包含 HTML（纯 CSS + 内联 SVG，零外部依赖，禁止 CDN/外链字体/外链 JS）
- 结构：左侧深色导航栏（logo+菜单）、顶部栏（标题+用户）、Dashboard KPI 卡片区
  （至少 4 张：数值+趋势箭头+环形进度）、至少 2 个内联 SVG 图表（折线图含坐标轴与
  图例、环形图含百分比）、数据表格（状态徽标 + 三档数值）、告警列表
- 配色：主色 #2563eb 蓝、辅色 #0f172a 深蓝黑、成功 #16a34a、告警 #f59e0b、危险 #dc2626、
  背景 #f1f5f9，卡片白色圆角阴影
- 数据取自以下拆标技术参数与 PRD（无数据时用「—」占位，不得编造具体数值）
- 输出仅 HTML 本身，不要 ``` 包裹、不要解释
[附：拆标技术参数 JSON、PRD 摘要、20 行高质量 HTML 锚示例]
```

失败/超时仍走 `_render_mockup_html` 规则版；成功 `source: "llm"`。

## 4. 前端横向流程（FR-23）

```
┌──────────────────────────────────────────────────────────────┐
│ [规范书上传卡片]  [投标模板卡片]        ← 顶部 grid-2           │
│                [ 开始生成 ]            ← 中间主按钮（触发pipeline）│
│ ①上传→②拆标→③需求→④假页面→⑤逐章→⑥组装   ← 横向步骤条            │
│   内容面板容器 overflow-x:auto + scroll-snap:x mandatory      │
│   每步完成 scrollTo({left: step.offsetLeft, behavior:'smooth'})│
└──────────────────────────────────────────────────────────────┘
```

- `bidding.html`：上传卡片区改为两卡片并排（规范书 + 模板）；移除「快捷生成」卡片
  （后端 /generate 保留兼容）；「合规自检」按钮并入组装面板
- `startPipeline()`：POST /pipeline/run → 轮询 /pipeline/status（1s）→ 每阶段
  高亮 + 自动滑动；停 review 时展开逐章复核面板
- 逐章面板保留左右对照编辑器；全部确认后按钮变为「一键组装」

## 5. 测试

| 用例 | 覆盖 |
|------|------|
| test_bid_pipeline_run | 顺序执行各阶段、默认停 awaiting_review |
| test_bid_pipeline_auto_confirm | auto_confirm=True 完成组装+导出 |
| test_bid_pipeline_without_files_rejected | 未上传规范书 400 |
| test_bid_screenshot_embed | docx 含图片（无浏览器 skip） |
| test_bid_mockup_llm_direct_html | LLM 直出 HTML 保存（mock LLM） |
