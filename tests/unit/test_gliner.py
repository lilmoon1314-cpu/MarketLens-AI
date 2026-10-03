"""Semantic conversion and failure handling without loading torch or model weights."""

import math

import pytest

from marketlens.adapters.gliner import GLiNERConfig, SemanticAnalyzer, convert
from marketlens.tools.collection import normalize_reviews


def output():
    return {
        "sentiment": {"label": "negative", "confidence": 0.9},
        "topics": [{"label": "quality", "confidence": 0.8}],
        "feedback_value": {"label": "actionable", "confidence": 0.7},
    }


def test_combined_conversion_and_topic_order():
    data = output()
    data["topics"] += [
        {"label": "pricing", "confidence": 0.6},
        {"label": "quality", "confidence": 0.9},
    ]
    result = convert("r1", data, True)
    assert result.sentiment == "negative"
    assert result.topics == ["pricing", "quality"]
    assert result.confidence.topics == {"pricing": 0.6, "quality": 0.9}
    assert result.processed and result.truncated


@pytest.mark.parametrize("score", [None, "0.9", True, -0.1, 1.1, math.nan, math.inf])
def test_no_fabricated_scores(score):
    data = output()
    data["sentiment"]["confidence"] = score
    result = convert("r", data, False)
    assert result.sentiment == "unknown"
    assert result.confidence.sentiment is None


def test_thresholds_unknown_and_unscored_other():
    data = output()
    data["sentiment"]["confidence"] = 0.49
    data["topics"] = [
        {"label": "unknown_topic", "confidence": 1},
        {"label": "quality", "confidence": 0.39},
    ]
    result = convert("r", data, False)
    assert result.sentiment == "unknown"
    assert result.confidence.sentiment == 0.49
    assert result.topics == ["other"]
    assert result.confidence.topics == {}
    # F06 routing additionally requires actionable >=0.60.
    data["feedback_value"]["confidence"] = 0.59
    assert convert("r", data, False).feedback_value == "actionable"


@pytest.mark.parametrize("data", [None, [], {}, {"sentiment": {}}])
def test_malformed_result_unprocessed(data):
    assert not convert("r", data, False).processed


class FakeBackend:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    def prepare(self, text):
        if text == "bad":
            raise ValueError("tokenizer error")
        return text[:4], len(text) > 4

    def extract(self, texts, batch_size):
        self.calls.append((list(texts), batch_size))
        if self.failures:
            self.failures -= 1
            raise RuntimeError("inference error")
        return [output() for _ in texts]


def test_batch_retry_truncation_preserves_reviews():
    backend = FakeBackend(failures=1)
    reviews = normalize_reviews([{"text": "长评论abcdef"}, {"text": "短文"}]).reviews
    before = [r.model_dump() for r in reviews]
    results = SemanticAnalyzer(GLiNERConfig(batch_size=8), backend).analyze(reviews)
    assert [size for _, size in backend.calls] == [8, 4]
    assert len(results) == 2
    assert results[0].truncated
    assert results[1].processed
    assert before == [r.model_dump() for r in reviews]
    assert [r.review_id for r in reviews] == [r.review_id for r in results]


def test_failed_batch_and_preparation_keep_unknown():
    backend = FakeBackend(failures=10)
    reviews = normalize_reviews([{"text": "bad"}, {"text": "长评论abcdef"}]).reviews
    results = SemanticAnalyzer(backend=backend).analyze(reviews)
    assert len(backend.calls) == 2
    assert all(not result.processed for result in results)
    assert all(result.confidence.feedback_value is None for result in results)
    assert results[1].truncated


def test_empty_input_does_not_load_model():
    backend = FakeBackend()
    assert SemanticAnalyzer(backend=backend).analyze([]) == []
    assert backend.calls == []


@pytest.mark.parametrize(
    "kwargs",
    [{"batch_size": 0}, {"batch_size": True}, {"splitter": "bad"}, {"label_language": "bad"}],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        GLiNERConfig(**kwargs)
