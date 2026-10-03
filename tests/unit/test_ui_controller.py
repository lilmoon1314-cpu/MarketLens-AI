import json

import pytest

from marketlens.tools.collection import MAX_UPLOAD_BYTES
from marketlens.ui.controller import export_report, sample_bytes, uploaded_dataset


def test_upload_generated_path_and_cleanup_even_on_failure(tmp_path):
    with (
        pytest.raises(RuntimeError),
        uploaded_dataset(b"text\nhello", "../../secret.csv", tmp_path) as datasets,
    ):
        path = datasets["upload"]
        assert path.parent == tmp_path / "uploads"
        assert path.name != "secret.csv"
        assert path.read_bytes() == b"text\nhello"
        raise RuntimeError("analysis failed")
    assert not path.exists()


@pytest.mark.parametrize(
    "data,name",
    [(b"", "data.csv"), (b"text", "data.exe"), (b"x" * (MAX_UPLOAD_BYTES + 1), "data.jsonl")],
    ids=["empty", "extension", "oversize"],
)
def test_upload_rejects_size_empty_and_extension(tmp_path, data, name):
    with pytest.raises(ValueError), uploaded_dataset(data, name, tmp_path):
        pytest.fail("invalid upload accepted")


def test_sample_is_bounded_valid_jsonl():
    values = [json.loads(line) for line in sample_bytes().splitlines()]
    assert len(values) == 12 and all(v["text"] for v in values)


def test_exports_omit_bodies_by_default(tmp_path):
    pytest.importorskip("langgraph")
    from marketlens.contracts import AnalysisRequest
    from marketlens.storage.sqlite import RunStore
    from marketlens.ui.controller import cited_ids
    from marketlens.workflow.demo import DemoAgents
    from marketlens.workflow.service import AnalysisService

    with uploaded_dataset(sample_bytes(), "sample.jsonl", tmp_path) as datasets:
        request = AnalysisRequest(
            product="phone",
            goal="feedback",
            sources=["local"],
            dataset_id="upload",
            product_urls=[],
            max_reviews=1000,
            report_language="zh-CN",
        )
        store = RunStore(tmp_path / "store.sqlite3")
        report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert "evidence" not in json.loads(export_report(report))
    evidence = store.evidence(report["run_id"], cited_ids(report))
    exported = json.loads(export_report(report, evidence))
    assert exported["evidence"][0]["text"] == evidence[0].text
    with pytest.raises(ValueError):
        export_report(report, [])
