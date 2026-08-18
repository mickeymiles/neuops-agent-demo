# -*- coding: utf-8 -*-
"""演示网页截图：playwright 懒加载渲染 outputs/*.html → mockup-shots/（NO-009 FR-15）

- 懒加载：首次调用才 import playwright；未安装依赖/浏览器/渲染失败 → 降级（不中断流水线）
- 输出：outputs/mockup-shots/shots.json（清单，带时间戳 TTL）+ p1-full.png（全页）+ p1-<n>-<slug>.png（分区）
- load_shots()：读取清单供组装 md 引用（assemble_document）与 docx 真插入（_add_demo_shot_table）
"""
import json
import os
import re
import time

from .bid_engine import BID_UPLOAD_ROOT

# 截图相对 outputs/ 的子目录名（组装 md 以此相对路径引用）
SHOT_DIR = "mockup-shots"
SHOT_DIR_REL = SHOT_DIR
# 截图缓存有效期（秒）：超过后视为失效，重新渲染
SHOT_TTL = 300
# 单次截图数量上限（避免 docx 过大）
SHOT_MAX = 8


def _mockup_output_dir(project_id: int) -> str:
    return os.path.join(BID_UPLOAD_ROOT, str(project_id), "outputs")


def _resolve_mockup_html(project_id: int):
    """找到最新的演示 HTML（kind=mockup 优先，否则 outputs/ 下最新 .html）；无则 None"""
    d = _mockup_output_dir(project_id)
    if not os.path.isdir(d):
        return None
    htmls = [f for f in os.listdir(d) if f.endswith(".html")]
    if not htmls:
        return None
    htmls.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    return os.path.join(d, htmls[0])


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s or "").strip("-")
    return (s or "sec")[:24]


def _manifest_path(project_id: int) -> str:
    return os.path.join(_mockup_output_dir(project_id), SHOT_DIR, "shots.json")


def load_shots(project_id: int) -> list:
    """读取截图清单（[{name,file,path,section}]）；无清单/过期/损坏返回 []"""
    try:
        with open(_manifest_path(project_id), encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - (data.get("ts") or 0) > SHOT_TTL:
            return []
        return [s for s in (data.get("shots") or []) if s.get("file")]
    except Exception:
        return []


def shot_mockup(project_id: int) -> dict:
    """渲染最新演示网页并截图（全页 + 分区）；返回 {shots, degraded, reason}
    - 无演示页 / playwright 未安装 / 浏览器未装 / 渲染失败 → degraded=True，不抛异常
    """
    html_path = _resolve_mockup_html(project_id)
    if not html_path:
        return {"shots": [], "degraded": True, "reason": "no_mockup"}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # 未安装 playwright 依赖
        return {"shots": [], "degraded": True, "reason": f"playwright 未安装: {e}"}

    out_dir = os.path.join(_mockup_output_dir(project_id), SHOT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    manifest = {"ts": time.time(), "shots": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"file://{html_path}", wait_until="load")
            page.wait_for_timeout(600)  # 等内联图表/字体渲染
            # 1) 全页截图
            full = os.path.join(out_dir, "p1-full.png")
            page.screenshot(path=full, full_page=True)
            manifest["shots"].append(
                {"name": "全部页面", "file": "p1-full.png", "path": full, "section": "full"})
            # 2) 分区截图（<section id="...">）
            secs = page.query_selector_all("section[id]")
            for i, sec in enumerate(secs[:SHOT_MAX], 1):
                fid = sec.get_attribute("id") or f"page-{i}"
                fname = f"p1-{i}-{_slug(fid)}.png"
                fpath = os.path.join(out_dir, fname)
                sec.screenshot(path=fpath)
                manifest["shots"].append(
                    {"name": fid, "file": fname, "path": fpath, "section": fid})
            browser.close()
    except Exception as e:  # 浏览器未安装 / 渲染失败 → 清理半成品并降级
        for s in manifest["shots"]:
            try:
                os.remove(s["path"])
            except Exception:
                pass
        return {"shots": [], "degraded": True, "reason": f"浏览器截图失败: {e}"}

    try:
        with open(_manifest_path(project_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"shots": manifest["shots"], "degraded": False, "reason": ""}
