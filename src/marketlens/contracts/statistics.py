"""Program-computed distributions with explicit sample denominators."""

from typing import Annotated, Literal

from pydantic import Field

from .models import Contract, Topic

Count = Annotated[int, Field(ge=0)]


class Statistics(Contract):
    raw_count: Count
    valid_count: Count
    rejected_counts: dict[str, Count]
    annotated_count: Count
    unprocessed_count: Count
    unknown_count: Count
    spam_count: Count
    truncated_count: Count
    low_sample: bool
    product_denominator: Count
    value_denominator: Count
    sentiment_distribution: dict[
        Literal["positive", "negative", "neutral", "mixed", "unknown"], Count
    ]
    topic_distribution: dict[Topic | Literal["unknown"], Count]
    feedback_value_distribution: dict[
        Literal["actionable", "non_actionable", "spam", "unknown"], Count
    ]
