"""Persistent reports, cache isolation, transactions, and safe workflow fallback."""

import json
import sqlite3
from copy import deepcopy

import pytest

pytest.importorskip("langgraph")
from langgraph.checkpoint.sqlite import SqliteSaver

from marketlens.contracts import AnalysisReport, AnalysisRequest
from marketlens.storage.sqlite import RunStore, semantic_cache_key
from marketlens.workflow.demo import DemoAgents, DemoSemantic
from marketlens.workflow.service import AnalysisService


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "reviews.jsonl"
    path.write_text("".join(json.dumps({"text": f"review{i}"}) + "\n" for i in range(10)))
    request = AnalysisRequest(
        product="phone",
        goal="feedback",
        sources=["local"],
        dataset_id="fixture",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )
    store = RunStore(tmp_path / "runs.sqlite3")
    return request, store, {"fixture": path}


def test_report_checkpoint_history_evidence_and_deletion(setup):
    request, store, datasets = setup
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert report["persisted"] is True
    run_id = report["run_id"]
    assert store.report(run_id).model_dump(mode="json") == report
    assert store.history()[0]["product"] == "phone"
    assert store.state(run_id)["stage"] == "finalize"
    selected = report["selected_ids"]
    assert [r.review_id for r in store.evidence(run_id, selected, for_llm=True)] == selected
    outside = next(
        r["review_id"] for r in store.state(run_id)["reviews"] if r["review_id"] not in selected
    )
    with pytest.raises(ValueError):
        store.evidence(run_id, [outside], for_llm=True)
    assert store.evidence(run_id, [outside])
    with pytest.raises(ValueError):
        store.evidence(run_id, ["not-in-run"])
    with SqliteSaver.from_conn_string(str(store.checkpoint_path)) as saver:
        assert saver.get_tuple({"configurable": {"thread_id": run_id}}) is not None
    store.delete_run(run_id)
    assert store.history() == [] and store.report(run_id) is None
    with SqliteSaver.from_conn_string(str(store.checkpoint_path)) as saver:
        assert saver.get_tuple({"configurable": {"thread_id": run_id}}) is None
    with store.connection() as db:
        for table in ("reviews", "annotations", "semantic_cache", "cache_refs"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_transaction_rollback_preserves_previous_snapshot(setup):
    request, store, datasets = setup
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    original = store.state(report["run_id"])
    corrupted = deepcopy(original)
    corrupted["status"] = "partial"
    corrupted["annotations"][0]["review_id"] = "foreign-review"
    corrupted["metrics"].pop("semantic_cache")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_state(corrupted)
    assert store.state(report["run_id"]) == original
    assert (
        len(store.evidence(report["run_id"], [r["review_id"] for r in original["reviews"]])) == 10
    )


def test_cache_reuses_only_versioned_semantics_and_keeps_shared_refs(setup):
    request, store, datasets = setup

    class Counting(DemoSemantic):
        calls = []

        def analyze(self, reviews):
            self.calls.append(len(reviews))
            return super().analyze(reviews)

    backend = Counting()
    first = AnalysisService(datasets, DemoAgents(), backend, store=store).run(request)
    second = AnalysisService(datasets, DemoAgents(), backend, store=store).run(request)
    assert backend.calls == [10]
    assert second["metrics"]["cache_hits"] == 10
    assert first["metrics"]["cache_hits"] == 0
    state = store.state(first["run_id"])
    text = state["reviews"][0]["text"]
    meta = first["metrics"]["semantic_cache"]
    assert store.cached(text, meta, "new-id").review_id == "new-id"
    for changed in (
        {**meta, "revision": "new"},
        {**meta, "language": "en"},
        {**meta, "splitter": "whitespace"},
        {**meta, "prompts": ["new"]},
    ):
        assert store.cached(text, changed, "new-id") is None
    assert store.cached(text + "changed", meta, "new-id") is None
    store.delete_run(first["run_id"])
    assert store.cached(text, meta, "new-id") is not None
    store.delete_run(second["run_id"])
    assert store.cached(text, meta, "new-id") is None


def test_corrupt_cache_is_miss(setup):
    request, store, datasets = setup
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    state = store.state(report["run_id"])
    text = state["reviews"][0]["text"]
    meta = report["metrics"]["semantic_cache"]
    with store.connection() as db:
        db.execute(
            "UPDATE semantic_cache SET payload=? WHERE cache_key=?",
            ('{"invalid":true}', semantic_cache_key(text, meta)),
        )
    assert store.cached(text, meta, "id") is None
    second = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert second["metrics"]["cache_hits"] == 9
    assert second["metrics"]["cache_misses"] == 1


def test_write_failure_returns_memory_report(setup, monkeypatch):
    request, store, datasets = setup

    def fail(state):
        raise sqlite3.OperationalError("private filesystem details")

    monkeypatch.setattr(store, "save_state", fail)
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert report["review_count"] == 10 and report["persisted"] is False
    assert any(w["code"] == "storage_failed" for w in report["warnings"])
    assert "private filesystem" not in json.dumps(report)


def test_checkpoint_failure_never_replays_agent_calls(setup, monkeypatch):
    request, store, datasets = setup

    class Counting(DemoAgents):
        calls = 0

        def planner(self, data):
            self.calls += 1
            return super().planner(data)

    agents = Counting()
    original = SqliteSaver.put

    def fail(self, config, checkpoint, metadata, new_versions):
        if metadata.get("step", -1) >= 1:
            raise sqlite3.OperationalError("secret error")
        return original(self, config, checkpoint, metadata, new_versions)

    monkeypatch.setattr(SqliteSaver, "put", fail)
    report = AnalysisService(datasets, agents, store=store).run(request)
    assert agents.calls == 1
    assert report["status"] in {"partial", "failed"}
    assert any(w["code"] == "checkpoint_failed" for w in report["warnings"])
    assert "secret error" not in json.dumps(report)


def test_final_report_contract_rejects_inconsistent_counts_and_evidence(setup):
    request, store, datasets = setup
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    for mutate in (
        lambda r: r.update(raw_count=999),
        lambda r: r["insights"][0].update(evidence_ids=["foreign"]),
        lambda r: r["selection"].update(strict_cap=10),
    ):
        invalid = deepcopy(report)
        mutate(invalid)
        with pytest.raises(ValueError):
            AnalysisReport.model_validate_json(json.dumps(invalid))


def test_final_write_failure_does_not_claim_persistence(setup, monkeypatch):
    request, store, datasets = setup
    original = store.save_state

    def fail_final(state):
        if state["report"] is not None:
            raise sqlite3.OperationalError("disk full")
        return original(state)

    monkeypatch.setattr(store, "save_state", fail_final)
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert report["persisted"] is False
    assert store.report(report["run_id"]) is None
    assert any(w["code"] == "storage_failed" for w in report["warnings"])


def test_checkpoint_initialization_failure_keeps_normal_analysis(setup, monkeypatch):
    request, store, datasets = setup

    def fail(self):
        raise sqlite3.OperationalError("checkpoint unavailable")

    monkeypatch.setattr(SqliteSaver, "setup", fail)
    report = AnalysisService(datasets, DemoAgents(), store=store).run(request)
    assert report["review_count"] == 10
    assert report["persisted"] is True
    assert any(w["code"] == "checkpoint_unavailable" for w in report["warnings"])
