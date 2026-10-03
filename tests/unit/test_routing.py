"""Budget and whitelist invariants, with hand-counted topic strata."""

import pytest

from marketlens.adapters.gliner import convert, unknown
from marketlens.tools.collection import normalize_reviews
from marketlens.tools.routing import (
    RoutingBudget,
    select_reviews,
    selected_evidence,
    strict_review_cap,
)


def fixtures(count, topic="quality"):
    reviews = normalize_reviews([{"text": f"评论{i}"} for i in range(count)]).reviews
    annotations = [
        convert(
            r.review_id,
            {
                "sentiment": {"label": "positive", "confidence": 0.9},
                "topics": [{"label": topic, "confidence": 0.8}],
                "feedback_value": {"label": "actionable", "confidence": 0.9},
            },
            False,
        )
        for r in reviews
    ]
    return reviews, annotations


@pytest.mark.parametrize("count,cap", [(0, 0), (1, 0), (3, 0), (4, 1), (10, 2), (1000, 299)])
def test_strict_cap_boundaries(count, cap):
    assert strict_review_cap(count) == cap


def test_strict_cap_for_entire_mvp_range():
    for count in range(1, 1001):
        cap = strict_review_cap(count)
        assert cap * 10 < count * 3
        assert (cap + 1) * 10 >= count * 3


def test_stratification_largest_remainder_and_permutation():
    reviews, annotations = fixtures(100)
    for index, item in enumerate(annotations[:30]):
        topic = "pricing" if index < 20 else "quality" if index < 28 else "delivery"
        item.topics = [topic]
        item.confidence.topics = {topic: 0.8}
    for item in annotations[30:]:
        item.feedback_value = "non_actionable"
    result = select_reviews(reviews, annotations)
    topics = {item.review_id: item.topics[0] for item in annotations}
    selected_topics = [topics[review_id] for review_id in result["selected_ids"]]
    assert {topic: selected_topics.count(topic) for topic in set(selected_topics)} == {
        "pricing": 19,
        "quality": 8,
        "delivery": 2,
    }
    assert len(result["selected_ids"]) == 29
    assert result == select_reviews(list(reversed(reviews)), list(reversed(annotations)))


def test_threshold_processed_and_primary_topic_tie():
    reviews, annotations = fixtures(10)
    annotations[0].confidence.feedback_value = 0.59
    annotations[1].processed = False
    annotations[2].feedback_value = "spam"
    annotations[3].confidence.feedback_value = None
    annotations[4] = unknown(reviews[4].review_id)
    annotations[5].confidence.feedback_value = 0.6
    annotations[5].topics = ["quality", "pricing"]
    annotations[5].confidence.topics = {"quality": 0.8, "pricing": 0.8}
    result = select_reviews(reviews, annotations)
    assert len(result["candidate_ids"]) == 5
    assert reviews[5].review_id in result["selected_ids"]  # one pricing stratum
    assert len(result["selected_ids"]) == 2


def test_complete_long_comment_is_skipped_without_truncation():
    reviews, annotations = fixtures(4)
    reviews[0].text = "长" * 10000
    annotations[0].confidence.feedback_value = 1.0
    result = select_reviews(reviews, annotations)
    assert reviews[0].review_id in result["token_skipped_ids"]
    assert reviews[0].review_id not in result["selected_ids"]
    assert len(result["selected_ids"]) == 1
    assert len(reviews[0].text) == 10000


def test_token_run_batch_and_zero_budget_limits():
    reviews, annotations = fixtures(1000)
    result = select_reviews(reviews, annotations, RoutingBudget(remaining_run_tokens=10000))
    assert result["estimated_run_tokens"] <= 10000
    assert all(n <= 8000 for n in result["batch_estimated_input_tokens"])
    assert all(len(batch) <= 20 for batch in result["batches"])
    assert [review_id for batch in result["batches"] for review_id in batch] == result[
        "selected_ids"
    ]
    assert result["token_count_method"] == "estimated_utf8_bytes"
    assert (
        select_reviews(reviews, annotations, RoutingBudget(remaining_run_tokens=0))["selected_ids"]
        == []
    )
    assert select_reviews(reviews, annotations, RoutingBudget(input_tokens=0))["selected_ids"] == []
    assert (
        len(
            select_reviews(
                reviews,
                annotations,
                RoutingBudget(
                    input_tokens=100000,
                    reserved_input_tokens=0,
                    output_tokens=0,
                    remaining_run_tokens=1000000,
                ),
            )["selected_ids"]
        )
        == 299
    )


def test_no_candidate_or_missing_annotations():
    reviews, _ = fixtures(10)
    assert select_reviews(reviews, [unknown(r.review_id) for r in reviews])["selected_ids"] == []
    assert select_reviews(reviews, [])["candidate_ids"] == []


@pytest.mark.parametrize("case", ["duplicate_review", "duplicate_annotation", "foreign_annotation"])
def test_invalid_identity_inputs(case):
    reviews, annotations = fixtures(4)
    if case == "duplicate_review":
        reviews.append(reviews[0])
    elif case == "duplicate_annotation":
        annotations.append(annotations[0])
    else:
        annotations.append(unknown("foreign"))
    with pytest.raises(ValueError):
        select_reviews(reviews, annotations)


def test_evidence_cannot_expand_fixed_whitelist():
    reviews, _ = fixtures(4)
    allowed = [reviews[0].review_id]
    assert selected_evidence(reviews, allowed, allowed) == [reviews[0]]
    for requested in [[reviews[1].review_id], ["foreign"], allowed * 2]:
        with pytest.raises(ValueError):
            selected_evidence(reviews, allowed, requested)
    with pytest.raises(ValueError):
        selected_evidence(reviews, ["foreign"], [])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_tokens": -1},
        {"output_tokens": True},
        {"batch_reviews": 21},
        {"remaining_run_tokens": 1.5},
    ],
)
def test_invalid_budgets(kwargs):
    with pytest.raises(ValueError):
        RoutingBudget(**kwargs)
