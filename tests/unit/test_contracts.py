"""Offline contract acceptance, schema parity, and reference integrity."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from marketlens.contracts import (
    AnalysisRequest,
    AnalystInput,
    ChartSpec,
    Insight,
    Review,
    SemanticReview,
)
from marketlens.contracts.export import AGENT_MODELS, export_schemas, schema_documents


@pytest.fixture
def examples():
    request = {
        "product": "降噪耳机",
        "goal": "识别舒适度问题",
        "sources": ["local", "taobao"],
        "dataset_id": "fixture-001",
        "product_urls": ["https://item.taobao.com/item.htm?id=123"],
        "max_reviews": 1000,
        "report_language": "zh-CN",
    }
    review = {
        "review_id": "r1",
        "text": "戴两小时耳朵会疼，希望减轻重量。",
        "source": "taobao",
        "source_id": None,
        "product_id": "123",
        "url": "https://item.taobao.com/item.htm?id=123",
        "time": "2026-10-01T12:00:00Z",
    }
    semantic = {
        "review_id": "r1",
        "sentiment": "negative",
        "topics": ["usability"],
        "feedback_value": "actionable",
        "confidence": {"sentiment": 0.9, "feedback_value": 0.8, "topics": {"usability": 0.9}},
        "processed": True,
        "truncated": False,
    }
    insight = {
        "kind": "pain_point",
        "title": "长时间佩戴不适",
        "summary": "入选评论提到耳朵疼。",
        "evidence_ids": ["r1"],
        "hypothesis": None,
    }
    chart = {
        "chart": "bar",
        "title": "反馈主题",
        "dataset": "topic_distribution",
        "x": "label",
        "y": "count",
    }
    return {
        "PlannerInput": {"request": request, "available_sources": ["local", "taobao"]},
        "PlannerOutput": {
            "sources": ["local", "taobao"],
            "keywords": ["降噪耳机"],
            "dimensions": ["pain_point", "feature_request"],
        },
        "AnalystInput": {
            "product": "降噪耳机",
            "goal": "识别舒适度问题",
            "dimensions": ["pain_point"],
            "report_language": "zh-CN",
            "reviews": [{"review": review, "semantic": semantic}],
        },
        "AnalystOutput": {"summary": "有佩戴不适反馈。", "insights": [insight], "limitations": []},
        "VisualizationInput": {
            "product": "降噪耳机",
            "report_language": "zh-CN",
            "available_metrics": [
                {
                    "dataset": "topic_distribution",
                    "label_field": "label",
                    "value_field": "count",
                }
            ],
            "insight_titles": ["长时间佩戴不适"],
        },
        "VisualizationOutput": {"charts": [chart]},
    }


@pytest.mark.parametrize("model", AGENT_MODELS)
def test_agent_json_roundtrip_and_schema(model, examples):
    payload = examples[model.__name__]
    parsed = model.model_validate_json(json.dumps(payload, ensure_ascii=False))
    serialized = parsed.model_dump(mode="json")
    assert model.model_validate_json(parsed.model_dump_json()) == parsed
    assert serialized == payload
    schema = schema_documents()[f"{model.__name__}.schema.json"]
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(serialized)
    bundle = schema_documents()["agent-contracts.schema.json"]
    entry_schema = {**bundle, "$ref": f"#/$defs/{model.__name__}"}
    Draft202012Validator(entry_schema, format_checker=FormatChecker()).validate(serialized)


@pytest.mark.parametrize("model", AGENT_MODELS)
def test_agent_rejects_extra_and_missing_fields(model, examples):
    payload = deepcopy(examples[model.__name__])
    payload["unexpected"] = "not allowed"
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
    del payload["unexpected"]
    del payload[next(iter(payload))]
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_reviews", 0),
        ("max_reviews", 1001),
        ("max_reviews", "10"),
        ("max_reviews", True),
        ("sources", ["reddit"]),
        ("sources", []),
        ("sources", ["local", "local"]),
        ("product", "   "),
        ("report_language", "fr"),
        ("product_urls", ["javascript:alert(1)"]),
        ("product_urls", ["https://u:p@example.com"]),
        ("product_urls", ["https://example.com:99999"]),
        ("product_urls", ["https://example.com"] * 2),
        ("product_urls", [f"https://example.com/{n}" for n in range(11)]),
        ("dataset_id", None),
        ("product_urls", []),
    ],
)
def test_request_rejects_invalid_inputs(field, value, examples):
    payload = deepcopy(examples["PlannerInput"]["request"])
    payload[field] = value
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate_json(json.dumps(payload))


def test_single_source_nullable_inputs(examples):
    request = deepcopy(examples["PlannerInput"]["request"])
    request.update(sources=["local"], product_urls=[])
    AnalysisRequest.model_validate(request)
    request.update(
        sources=["taobao"],
        dataset_id=None,
        product_urls=["https://item.taobao.com/item.htm?id=123"],
    )
    AnalysisRequest.model_validate(request)


@pytest.mark.parametrize("time", ["bad-date", "2026-10-01T12:00:00", "2026-10-01T12:00:00+08:00"])
def test_review_requires_utc(time, examples):
    review = deepcopy(examples["AnalystInput"]["reviews"][0]["review"])
    review["time"] = time
    with pytest.raises(ValidationError):
        Review.model_validate_json(json.dumps(review))


def test_review_unknown_provenance_and_nested_extra_fields(examples):
    review = deepcopy(examples["AnalystInput"]["reviews"][0]["review"])
    review.update(time=None, url=None, source_id=None, product_id=None)
    Review.model_validate(review)
    review["author"] = "unnecessary personal data"
    with pytest.raises(ValidationError):
        Review.model_validate(review)


def test_nullable_provenance_fields_are_required(examples):
    review = deepcopy(examples["AnalystInput"]["reviews"][0]["review"])
    del review["time"]
    with pytest.raises(ValidationError):
        Review.model_validate_json(json.dumps(review))


def test_nested_objects_and_boolean_types_are_strict(examples):
    semantic = deepcopy(examples["AnalystInput"]["reviews"][0]["semantic"])
    semantic["confidence"]["invented_score"] = 0.7
    with pytest.raises(ValidationError):
        SemanticReview.model_validate(semantic)
    del semantic["confidence"]["invented_score"]
    semantic["processed"] = 1
    with pytest.raises(ValidationError):
        SemanticReview.model_validate(semantic)
    semantic["processed"] = True
    semantic["topics"] = ["quality", "quality"]
    with pytest.raises(ValidationError):
        SemanticReview.model_validate(semantic)


@pytest.mark.parametrize("score", [-0.01, 1.01, "0.9", True, float("nan"), float("inf")])
def test_invalid_confidence_rejected(score, examples):
    semantic = deepcopy(examples["AnalystInput"]["reviews"][0]["semantic"])
    semantic["confidence"]["sentiment"] = score
    with pytest.raises(ValidationError):
        SemanticReview.model_validate(semantic)


def test_unknown_scores_and_invalid_topic_keys(examples):
    semantic = deepcopy(examples["AnalystInput"]["reviews"][0]["semantic"])
    semantic.update(sentiment="unknown", feedback_value="unknown", topics=[], processed=False)
    semantic["confidence"] = {"sentiment": None, "feedback_value": None, "topics": {}}
    SemanticReview.model_validate(semantic)
    semantic["confidence"]["topics"] = {"invented_topic": 0.9}
    with pytest.raises(ValidationError):
        SemanticReview.model_validate(semantic)


def test_analyst_reference_and_duplicate_id_integrity(examples):
    payload = deepcopy(examples["AnalystInput"])
    payload["reviews"][0]["semantic"]["review_id"] = "different"
    with pytest.raises(ValidationError, match="must match"):
        AnalystInput.model_validate_json(json.dumps(payload))
    payload = deepcopy(examples["AnalystInput"])
    payload["reviews"].append(deepcopy(payload["reviews"][0]))
    with pytest.raises(ValidationError, match="unique"):
        AnalystInput.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("ids", [[], ["r1", "r1"], [""]])
def test_insight_requires_nonempty_unique_evidence(ids, examples):
    insight = deepcopy(examples["AnalystOutput"]["insights"][0])
    insight["evidence_ids"] = ids
    with pytest.raises(ValidationError):
        Insight.model_validate(insight)


@pytest.mark.parametrize(
    "field,value",
    [
        ("chart", "donut"),
        ("dataset", "arbitrary_dataset"),
        ("x", "text"),
        ("y", "percent"),
    ],
)
def test_chart_rejects_invalid_bindings(field, value, examples):
    chart = deepcopy(examples["VisualizationOutput"]["charts"][0])
    chart[field] = value
    with pytest.raises(ValidationError):
        ChartSpec.model_validate(chart)


def test_schema_export_is_valid_and_reproducible(tmp_path):
    export_schemas(tmp_path)
    documents = schema_documents()
    assert len(documents) == 8
    committed = Path(__file__).resolve().parents[2] / "docs" / "schemas"
    for name, schema in documents.items():
        Draft202012Validator.check_schema(schema)
        assert json.loads((tmp_path / name).read_text(encoding="utf-8")) == schema
        assert (committed / name).read_bytes() == (tmp_path / name).read_bytes()
        _assert_references_resolve(schema, schema)
        _assert_objects_forbid_extra(schema)


def _assert_references_resolve(node, root):
    if isinstance(node, dict):
        if "$ref" in node:
            target = root
            for segment in node["$ref"].removeprefix("#/").split("/"):
                target = target[segment]
        for value in node.values():
            _assert_references_resolve(value, root)
    elif isinstance(node, list):
        for value in node:
            _assert_references_resolve(value, root)


def _assert_objects_forbid_extra(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            assert node["additionalProperties"] is False
        for value in node.values():
            _assert_objects_forbid_extra(value)
    elif isinstance(node, list):
        for value in node:
            _assert_objects_forbid_extra(value)
