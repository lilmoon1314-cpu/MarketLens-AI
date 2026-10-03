"""Hand-counted fixtures for spam, unknown, and overlapping topic denominators."""

import pytest

from marketlens.adapters.gliner import convert, unknown
from marketlens.tools.collection import normalize_reviews
from marketlens.tools.statistics import aggregate_statistics


def annotation(review, sentiment="positive", value="actionable", topics=("quality",)):
    return convert(
        review.review_id,
        {
            "sentiment": {"label": sentiment, "confidence": 0.9},
            "feedback_value": {"label": value, "confidence": 0.8},
            "topics": [{"label": topic, "confidence": 0.7} for topic in topics],
        },
        False,
    )


def test_hand_counted_overlap_spam_unknown_and_missing():
    reviews = normalize_reviews([{"text": f"评论{i}"} for i in range(5)]).reviews
    annotations = [
        annotation(reviews[0], topics=("quality", "delivery", "packaging")),
        annotation(reviews[1], sentiment="negative", topics=("quality", "pricing")),
        annotation(reviews[2], value="spam"),
        unknown(reviews[3].review_id, True),
    ]
    result = aggregate_statistics(reviews, annotations, 7, {"duplicate": 2})
    assert result.valid_count == 5 and result.raw_count == 7
    assert result.annotated_count == 3 and result.unprocessed_count == 2
    assert result.spam_count == 1 and result.product_denominator == 4
    assert result.value_denominator == 5 and result.unknown_count == 2
    assert result.truncated_count == 1 and result.low_sample
    assert result.sentiment_distribution == {
        "positive": 1,
        "negative": 1,
        "neutral": 0,
        "mixed": 0,
        "unknown": 2,
    }
    assert result.feedback_value_distribution == {
        "actionable": 2,
        "non_actionable": 0,
        "spam": 1,
        "unknown": 2,
    }
    assert result.topic_distribution["quality"] == 2
    assert sum(result.topic_distribution.values()) == 7  # multi-label, not a partition
    assert result == aggregate_statistics(
        list(reversed(reviews)), list(reversed(annotations)), 7, {"duplicate": 2}
    )


def test_empty_all_spam_and_sample_boundary():
    result = aggregate_statistics([], [], 0, {})
    assert result.product_denominator == 0
    reviews = normalize_reviews([{"text": f"评论{i}"} for i in range(20)]).reviews
    result = aggregate_statistics(reviews, [annotation(r, value="spam") for r in reviews], 20, {})
    assert result.product_denominator == 0 and not result.low_sample
    assert sum(result.sentiment_distribution.values()) == 0
    assert result.feedback_value_distribution["spam"] == 20


def test_unprocessed_labels_cannot_affect_counts():
    review = normalize_reviews([{"text": "评论"}]).reviews[0]
    semantic = annotation(review, value="spam").model_copy(update={"processed": False})
    result = aggregate_statistics([review], [semantic], 1, {})
    assert result.spam_count == 0
    assert result.sentiment_distribution["unknown"] == 1
    assert result.feedback_value_distribution["unknown"] == 1


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_review",
        "duplicate_annotation",
        "foreign_id",
        "raw_count",
        "negative_count",
        "bool_count",
    ],
)
def test_inconsistent_inputs_rejected(case):
    review = normalize_reviews([{"text": "评论"}]).reviews[0]
    reviews, annotations, raw, rejected = [review], [], 1, {}
    if case == "duplicate_review":
        reviews *= 2
    elif case == "duplicate_annotation":
        annotations = [annotation(review)] * 2
    elif case == "foreign_id":
        annotations = [unknown("foreign")]
    elif case == "raw_count":
        raw = 2
    elif case == "negative_count":
        rejected = {"bad": -1}
    else:
        raw = True
    with pytest.raises(ValueError):
        aggregate_statistics(reviews, annotations, raw, rejected)
