"""Exercise the actual Streamlit script without external inference calls."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parents[2] / "src/marketlens/ui/app.py"


def click(app, label):
    return next(b for b in app.button if b.label == label).click().run(timeout=20)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETLENS_DATA_DIR", str(tmp_path))
    return AppTest.from_file(str(APP)).run(timeout=20)


def test_demo_report_evidence_export_history_and_delete(app):
    assert not app.exception
    click(app, "开始分析")
    assert not app.exception and not app.error
    assert app.session_state["report"]["mode"] == "demo"
    assert app.session_state["report"]["request"]["dataset_id"] == "demo-sample"
    assert any("合成评论样例" in i.value for i in app.info)
    assert app.session_state["report"]["persisted"] is True
    assert any(m.label == "有效评论" and m.value == "12" for m in app.metric)
    assert any(e.label == "查看原始评论证据" for e in app.expander)
    assert len(app.text) > 0
    app.run(timeout=20)
    history = next(s for s in app.selectbox if s.label == "选择历史报告")
    run_id = app.session_state["report"]["run_id"]
    history.select(run_id).run(timeout=20)
    click(app, "查看报告")
    assert app.session_state["report"]["run_id"] == run_id
    next(c for c in app.checkbox if c.label == "确认删除所选运行及其证据").check().run()
    click(app, "删除记录")
    assert "report" not in app.session_state
    assert not app.exception


def test_upload_required_and_invalid_request(app):
    next(r for r in app.radio if r.label == "评论数据").set_value("上传文件").run()
    click(app, "开始分析")
    assert any("请选择评论文件" in e.value for e in app.error)
    next(r for r in app.radio if r.label == "评论数据").set_value("演示样例").run()
    app.text_input[0].set_value(" ").run()
    click(app, "开始分析")
    assert app.error and not app.exception


def test_partial_zero_data_report_is_renderable(app, tmp_path):
    from marketlens.contracts import AnalysisRequest
    from marketlens.workflow.demo import DemoAgents
    from marketlens.workflow.service import AnalysisService

    path = tmp_path / "empty.jsonl"
    path.write_text("")
    request = AnalysisRequest(
        product="empty",
        goal="feedback",
        sources=["local"],
        dataset_id="empty",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )
    app.session_state["report"] = AnalysisService({"empty": path}, DemoAgents()).run(request)
    app.run(timeout=20)
    assert not app.exception
    assert any("暂无证据洞察" in info.value for info in app.info)
    assert any("尚无可绘制" in info.value for info in app.info)
