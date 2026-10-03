"""Run actual compiled LangGraph against offline agent fixtures."""

import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("langgraph")

from marketlens.contracts import AnalysisRequest
from marketlens.workflow.demo import DemoAgents
from marketlens.workflow.service import AnalysisService


@pytest.fixture
def analysis_request():
    return AnalysisRequest(
        product="示例产品",
        goal="了解反馈",
        sources=["local"],
        dataset_id="fixture",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )


def dataset(tmp_path, count):
    path = tmp_path / "reviews.jsonl"
    path.write_text(
        "".join(json.dumps({"text": f"评论{i}"}) + "\n" for i in range(count)), encoding="utf-8"
    )
    return {"fixture": path}


def test_three_agents_and_serializable_report(tmp_path, analysis_request):
    report = AnalysisService(dataset(tmp_path, 4), DemoAgents()).run(analysis_request)
    assert report["status"] == "complete"
    assert report["mode"] == "demo"
    assert report["review_count"] == 4
    assert len(report["selected_ids"]) == 1
    assert report["analyst_result"]["insights"][0]["evidence_ids"] == report["selected_ids"]
    assert report["visualization"]["charts"][0]["chart"] == "bar"
    assert report["warnings"][0]["code"] == "demo_mode"
    json.dumps(report)


@pytest.mark.parametrize("count,status", [(0, "insufficient_data"), (1, "partial"), (3, "partial")])
def test_no_data_or_no_budget_skips_agents(tmp_path, analysis_request, count, status):
    class NoAnalysis(DemoAgents):
        def analyst(self, data):
            raise AssertionError("must not run")

    report = AnalysisService(dataset(tmp_path, count), NoAnalysis()).run(analysis_request)
    assert report["status"] == status
    assert report["analyst_result"] is None
    assert report["selected_ids"] == []
    assert report["errors"] == []


@pytest.mark.parametrize(
    "stage,status", [("planner", "failed"), ("analyst", "partial"), ("visualization", "partial")]
)
def test_node_failure_preserves_data_and_hides_exception(tmp_path, analysis_request, stage, status):
    class Broken(DemoAgents):
        pass

    def fail(self, data):
        raise RuntimeError("private API key should never appear")

    setattr(Broken, stage, fail)
    report = AnalysisService(dataset(tmp_path, 5), Broken()).run(analysis_request)
    assert report["status"] == status
    assert report["errors"][0]["stage"] == stage
    assert "private API" not in json.dumps(report)
    assert report["review_count"] == (0 if stage == "planner" else 5)


def test_missing_dataset_is_failed_collection(tmp_path, analysis_request):
    report = AnalysisService({}, DemoAgents()).run(analysis_request)
    assert report["status"] == "failed"
    assert report["errors"][0]["stage"] == "collect"


def test_agent_cannot_expand_source_or_evidence(tmp_path, analysis_request):
    class WrongSource(DemoAgents):
        def planner(self, data):
            output = super().planner(data)
            return output.model_copy(update={"sources": ["taobao"]})

    class WrongEvidence(DemoAgents):
        def analyst(self, data):
            output = super().analyst(data)
            output.insights[0].evidence_ids = ["invented"]
            return output

    for agents, stage in [(WrongSource(), "planner"), (WrongEvidence(), "analyst")]:
        report = AnalysisService(dataset(tmp_path, 4), agents).run(analysis_request)
        assert report["errors"][0]["stage"] == stage
        assert report["analyst_result"] is None


def test_stream_order_and_runs_are_isolated(tmp_path, analysis_request):
    service = AnalysisService(dataset(tmp_path, 4), DemoAgents())
    events = list(service.stream(analysis_request))
    assert [event["stage"] for event in events] == [
        "start",
        "planner",
        "collect",
        "analyst",
        "visualization",
        "finalize",
    ]
    assert len({event["run_id"] for event in events}) == 1
    assert events[-1]["report"]["status"] == "complete"
    assert service.run(analysis_request)["run_id"] != events[0]["run_id"]
    assert all("reviews" not in event for event in events)


def test_cli_explicit_demo_and_exit_codes(tmp_path):
    path = dataset(tmp_path, 4)["fixture"]
    args = [
        sys.executable,
        "-m",
        "marketlens.cli",
        "analyze",
        "--input",
        str(path),
        "--product",
        "示例",
        "--goal",
        "反馈",
        "--demo",
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mode"] == "demo"
    assert subprocess.run(args[:-1], capture_output=True, check=False).returncode == 2
    path.unlink()
    result = subprocess.run(args, capture_output=True, check=False)
    assert result.returncode == 1
