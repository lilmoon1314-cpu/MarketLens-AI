"""Count all valid reviews; exclude spam only from product-facing distributions."""

from collections.abc import Mapping
from typing import get_args

from marketlens.contracts import Review, SemanticReview
from marketlens.contracts.models import Topic
from marketlens.contracts.statistics import Statistics


def aggregate_statistics(
    reviews: list[Review],
    annotations: list[SemanticReview],
    raw_count: int,
    rejected_counts: Mapping[str, int],
) -> Statistics:
    ids = {review.review_id for review in reviews}
    if len(ids) != len(reviews):
        raise ValueError("duplicate review IDs")
    by_id = {annotation.review_id: annotation for annotation in annotations}
    if len(by_id) != len(annotations) or not by_id.keys() <= ids:
        raise ValueError("annotations must have unique IDs belonging to reviews")
    if type(raw_count) is not int or any(
        type(n) is not int or n < 0 for n in rejected_counts.values()
    ):
        raise ValueError("counts must be nonnegative integers")
    if raw_count != len(reviews) + sum(rejected_counts.values()):
        raise ValueError("raw count must equal valid plus rejected")
    sentiments = dict.fromkeys(("positive", "negative", "neutral", "mixed", "unknown"), 0)
    topics = dict.fromkeys((*get_args(Topic), "unknown"), 0)
    values = dict.fromkeys(("actionable", "non_actionable", "spam", "unknown"), 0)
    processed = spam = truncated = 0
    for review in reviews:
        annotation = by_id.get(review.review_id)
        truncated += int(annotation is not None and annotation.truncated)
        if annotation is None or not annotation.processed:
            sentiments["unknown"] += 1
            topics["unknown"] += 1
            values["unknown"] += 1
            continue
        processed += 1
        values[annotation.feedback_value] += 1
        if annotation.feedback_value == "spam":
            spam += 1
            continue
        sentiments[annotation.sentiment] += 1
        for topic in annotation.topics or ["other"]:
            topics[topic] += 1
    return Statistics(
        raw_count=raw_count,
        valid_count=len(reviews),
        rejected_counts=dict(rejected_counts),
        annotated_count=processed,
        unprocessed_count=len(reviews) - processed,
        unknown_count=sentiments["unknown"],
        spam_count=spam,
        truncated_count=truncated,
        low_sample=len(reviews) < 20,
        product_denominator=len(reviews) - spam,
        value_denominator=len(reviews),
        sentiment_distribution=sentiments,
        topic_distribution=topics,
        feedback_value_distribution=values,
    )
