"""Manual visual acceptance: start Streamlit, then run this script with collector extra."""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).parents[2]
PICS = ROOT / "test/pic_test"
PICS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.goto("http://127.0.0.1:8501")
    page.add_style_tag(content="*{animation:none!important;transition:none!important}")
    page.get_by_role("button", name="开始分析", exact=True).wait_for()
    page.get_by_label("产品名称", exact=True).wait_for()
    page.screenshot(
        path=str(PICS / "dashboard-input-desktop-1440x1000.png"),
        full_page=True,
        animations="disabled",
    )
    page.get_by_text("上传文件", exact=True).click()
    expect(page.locator('input[type="file"]')).to_be_enabled()
    page.locator('input[type="file"]').set_input_files(
        {
            "name": "acceptance.jsonl",
            "mimeType": "application/jsonl",
            "buffer": "\n".join(
                json.dumps({"text": f"合成评论{i}：电量不够用，希望优化。"}, ensure_ascii=False)
                for i in range(12)
            ).encode(),
        }
    )
    page.get_by_text("acceptance.jsonl", exact=True).wait_for()
    page.get_by_role("button", name="开始分析", exact=True).click()
    page.get_by_role("heading", name="反馈分析报告", exact=True).wait_for(timeout=30000)
    page.get_by_text(
        "演示报告：语义标签与洞察来自模拟数据，不可用于产品决策。", exact=True
    ).wait_for()
    page.get_by_text("查看原始评论证据", exact=True).click()
    page.get_by_text("评论 ID：", exact=False).first.wait_for()
    page.get_by_text("评论 ID：", exact=False).first.scroll_into_view_if_needed()
    page.wait_for_timeout(1000)  # Allow native expander and rerun paint to settle.
    expect(page.locator('[data-stale="true"]')).to_have_count(0)
    page.screenshot(
        path=str(PICS / "dashboard-evidence-desktop-1440x1000.png"),
        full_page=True,
        animations="disabled",
    )
    page.get_by_role("tab", name="反馈分布", exact=True).click()
    page.get_by_test_id("stVegaLiteChart").first.wait_for()
    page.screenshot(
        path=str(PICS / "dashboard-charts-desktop-1440x1000.png"),
        full_page=True,
        animations="disabled",
    )
    page.get_by_role("tab", name="报告导出", exact=True).click()
    with page.expect_download() as download:
        page.get_by_role("button", name="下载 JSON 报告").click()
    result = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    assert result["review_count"] == 12 and result["persisted"]
    assert result["mode"] == "demo" and "evidence" not in result
    page.get_by_text("导出时附带已引用的评论正文", exact=True).click()
    page.get_by_text("本次导出附带评论正文", exact=True).wait_for()
    with page.expect_download() as download:
        page.get_by_role("button", name="下载 JSON 报告").click()
    result = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    assert result["evidence"] and all(e["text"] for e in result["evidence"])
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("tab", name="洞察与证据", exact=True).click()
    expect(page.locator('[data-stale="true"]')).to_have_count(0)
    if not page.get_by_text("评论 ID：", exact=False).first.is_visible():
        page.get_by_text("查看原始评论证据", exact=True).click()
    page.get_by_text("评论 ID：", exact=False).first.scroll_into_view_if_needed()
    page.wait_for_timeout(1000)  # Allow native expander and rerun paint to settle.
    expect(page.locator('[data-stale="true"]')).to_have_count(0)
    page.screenshot(
        path=str(PICS / "dashboard-evidence-mobile-390x844.png"),
        full_page=True,
        animations="disabled",
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_label("产品名称", exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(PICS / "dashboard-input-mobile-390x844.png"), animations="disabled")
    assert not page.get_by_test_id("stException").count()
    browser.close()
print("browser upload/evidence/charts/export/responsive acceptance passed")
