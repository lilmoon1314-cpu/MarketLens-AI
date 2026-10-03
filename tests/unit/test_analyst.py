"""Batch-scoped evidence, deterministic counting, and bounded partial recovery."""

import json

import pytest

from marketlens.adapters.llm import ProviderError, Response, StructuredLLM
from marketlens.agents.analyst import AnalystAgent
from marketlens.config import LLMConfig
from marketlens.contracts import AnalystInput, AnalystOutput, AnnotatedReview, Insight
from marketlens.prompts.analyst import SYSTEM
from marketlens.tools.collection import normalize_reviews
from marketlens.tools.evidence import insight_records, validate_insights
from marketlens.workflow.demo import DemoSemantic


def data(count=4):
    reviews = normalize_reviews(
        [{"text": f"电池只有两小时，评论{i}"} for i in range(count)]
    ).reviews
    semantics = DemoSemantic().analyze(reviews)
    return AnalystInput(
        product="耳机",
        goal="了解问题",
        dimensions=["pain_point"],
        report_language="zh-CN",
        reviews=[
            AnnotatedReview(review=r, semantic=s) for r, s in zip(reviews, semantics, strict=True)
        ],
    )


def insight(ids, title="电池续航短"):
    return Insight(
        kind="pain_point",
        title=title,
        summary="电池只用两小时。",
        evidence_ids=ids,
        hypothesis=None,
    )


class Backend:
    def __init__(self, failures=None, invalid=False, merge_failure=False):
        self.payloads = []
        self.failures = failures or set()
        self.invalid = invalid
        self.merge_failure = merge_failure

    def complete(self, messages, schema):
        payload = json.loads(messages[1]["content"])
        self.payloads.append(payload)
        if len(self.payloads) in self.failures or self.merge_failure and "insights" in payload:
            raise ProviderError(False)
        ids = (
            [item["review"]["review_id"] for item in payload["reviews"]]
            if "reviews" in payload
            else sorted(
                {review_id for item in payload["insights"] for review_id in item["evidence_ids"]}
            )
        )
        insights = [insight(ids)]
        if self.invalid:
            insights.append(insight(["invented"], "虚构问题"))
        output = AnalystOutput(
            summary="仅有样本支持的结论" if not self.invalid else "虚构问题100%发生。",
            insights=insights,
            limitations=[],
        )
        return Response(output.model_dump_json(), 100, 50)


def llm(backend, **limits):
    return StructuredLLM(
        LLMConfig("https://provider.example/v1", "fixture", "sanitized", **limits), backend
    )


def ids(payload):
    return [item.review.review_id for item in payload.reviews]


def test_batch_merge_preserves_whitelist_and_program_counts():
    payload = data(4)
    backend = Backend()
    result = AnalystAgent(llm(backend)).analyze(payload, [ids(payload)[:2], ids(payload)[2:]])
    assert result.warnings == []
    assert set(result.sent_ids) == set(ids(payload))
    assert len(backend.payloads) == 3
    assert "reviews" not in backend.payloads[-1]
    assert result.insights[0]["evidence_count"] == 4
    assert set(result.insights[0]["evidence_ids"]) == set(ids(payload))
    assert len(result.insights[0]["insight_id"]) == 64


def test_fake_reference_drops_whole_insight_and_rebuilds_summary():
    payload = data(2)
    backend = Backend(invalid=True)
    result = AnalystAgent(llm(backend)).analyze(payload, [ids(payload)])
    assert len(result.output.insights) == 1
    assert "100%" not in result.output.summary
    assert result.warnings[0]["code"] == "invalid_evidence"
    assert all("invented" not in item["evidence_ids"] for item in result.insights)


def test_partial_batch_failure_and_merge_fallback():
    payload = data(4)
    result = AnalystAgent(llm(Backend(failures={1}))).analyze(
        payload, [ids(payload)[:2], ids(payload)[2:]]
    )
    assert result.insights[0]["evidence_count"] == 2
    assert result.warnings[0]["code"] == "analyst_batch_failed"
    result = AnalystAgent(llm(Backend(merge_failure=True))).analyze(
        payload, [ids(payload)[:2], ids(payload)[2:]]
    )
    assert result.insights[0]["evidence_count"] == 4
    assert result.warnings[0]["code"] == "analyst_merge_fallback"


def test_actual_message_budget_refines_batch():
    payload = data(4)
    backend = Backend()
    instance = llm(backend)
    one = payload.model_copy(update={"reviews": payload.reviews[:1]})
    limit = instance.estimate_input(AnalystOutput, SYSTEM, one) + 20
    instance = llm(backend, input_tokens=limit)
    result = AnalystAgent(instance).analyze(payload, [ids(payload)])
    batch_payloads = [p for p in backend.payloads if "reviews" in p]
    assert len(batch_payloads) == 4
    assert all(len(p["reviews"]) == 1 for p in batch_payloads)
    assert set(result.sent_ids) == set(ids(payload))


def test_long_review_is_not_truncated_or_sent_and_empty_evidence_summary_safe():
    payload = data(2)
    payload.reviews[0].review.text = "长" * 10000
    backend = Backend()
    result = AnalystAgent(llm(backend)).analyze(payload, [ids(payload)])
    assert result.sent_ids == ids(payload)[1:]
    assert result.warnings[0]["code"] == "analyst_long_review"
    assert len(payload.reviews[0].review.text) == 10000
    output, _ = validate_insights(
        AnalystOutput(summary="所有用户都抱怨。", insights=[], limitations=[]), set()
    )
    assert "所有用户" not in output.summary


def test_no_remaining_budget_calls_nothing():
    payload = data(2)
    backend = Backend()
    instance = llm(backend, run_tokens=100)
    result = AnalystAgent(instance).analyze(payload, [ids(payload)])
    assert instance.calls == [] and backend.payloads == []
    assert result.sent_ids == [] and result.insights == []
    assert result.warnings[0]["code"] == "analyst_batch_failed"


@pytest.mark.parametrize("batches", [[[]], [["foreign"]], []])
def test_batches_cannot_change_selection(batches):
    with pytest.raises(ValueError, match="partition"):
        AnalystAgent(llm(Backend())).analyze(data(2), batches)


def test_overlap_deduplication_and_stable_ids():
    items = [insight(["r1"], " Ａ "), insight(["r2", "r1"], "A"), insight(["r1"], "另一个问题")]
    records = insight_records(items)
    assert sorted(item["evidence_count"] for item in records) == [1, 2]
    assert records == insight_records(list(reversed(items)))
