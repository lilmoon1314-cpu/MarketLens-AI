"""Validated business contracts; no model, network, or storage dependencies."""

from datetime import timedelta
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Source = Literal["local", "taobao"]
Language = Literal["zh-CN", "en"]
Dimension = Literal["strength", "weakness", "pain_point", "feature_request"]
Topic = Literal[
    "pricing",
    "performance",
    "reliability",
    "usability",
    "features",
    "support",
    "quality",
    "delivery",
    "packaging",
    "other",
]
Dataset = Literal[
    "sentiment_distribution",
    "topic_distribution",
    "feedback_value_distribution",
    "insight_evidence_counts",
]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must contain non-whitespace text")
    return value


def _unique[T](values: list[T]) -> list[T]:
    if len(values) != len(set(values)):
        raise ValueError("items must be unique")
    return values


def _web_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or any(char.isspace() for char in value)
    ):
        raise ValueError("must be an absolute HTTP(S) URL without credentials")
    # Access also validates malformed/out-of-range ports.
    _ = parts.port
    return value


def _utc(value: AwareDatetime) -> AwareDatetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("time must use UTC")
    return value


Text = Annotated[str, Field(min_length=1), AfterValidator(_nonblank)]
ShortText = Annotated[Text, Field(max_length=200)]
LongText = Annotated[Text, Field(max_length=2000)]
Score = Annotated[float, Field(ge=0, le=1)]
WebURL = Annotated[str, Field(json_schema_extra={"format": "uri"}), AfterValidator(_web_url)]
UTCTime = Annotated[AwareDatetime, AfterValidator(_utc)]
UniqueSources = Annotated[
    list[Source], AfterValidator(_unique), Field(json_schema_extra={"uniqueItems": True})
]
UniqueDimensions = Annotated[
    list[Dimension], AfterValidator(_unique), Field(json_schema_extra={"uniqueItems": True})
]


class Contract(BaseModel):
    """JSON types are strict; nullable fields remain required unless specified otherwise."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class AnalysisRequest(Contract):
    product: ShortText
    goal: LongText
    sources: Annotated[UniqueSources, Field(min_length=1)]
    dataset_id: Text | None
    product_urls: Annotated[
        list[WebURL],
        Field(max_length=10, json_schema_extra={"uniqueItems": True}),
        AfterValidator(_unique),
    ]
    max_reviews: Annotated[int, Field(ge=1, le=1000)]
    report_language: Language

    @model_validator(mode="after")
    def validate_source_inputs(self) -> Self:
        if "local" in self.sources and self.dataset_id is None:
            raise ValueError("local source requires dataset_id")
        if "taobao" in self.sources and not self.product_urls:
            raise ValueError("taobao source requires product_urls")
        return self


class Review(Contract):
    review_id: Text
    text: Text
    source: Source
    source_id: str | None
    product_id: str | None
    url: WebURL | None
    time: UTCTime | None


class PlannerInput(Contract):
    request: AnalysisRequest
    available_sources: UniqueSources


class PlannerOutput(Contract):
    sources: Annotated[UniqueSources, Field(min_length=1)]
    keywords: Annotated[
        list[Annotated[Text, Field(max_length=100)]],
        Field(min_length=1, max_length=8, json_schema_extra={"uniqueItems": True}),
        AfterValidator(_unique),
    ]
    dimensions: Annotated[UniqueDimensions, Field(min_length=1)]


class Confidence(Contract):
    sentiment: Score | None
    feedback_value: Score | None
    topics: dict[Topic, Score]


class SemanticReview(Contract):
    review_id: Text
    sentiment: Literal["positive", "negative", "neutral", "mixed", "unknown"]
    topics: Annotated[
        list[Topic], AfterValidator(_unique), Field(json_schema_extra={"uniqueItems": True})
    ]
    feedback_value: Literal["actionable", "non_actionable", "spam", "unknown"]
    confidence: Confidence
    processed: bool
    truncated: bool


class AnnotatedReview(Contract):
    review: Review
    semantic: SemanticReview

    @model_validator(mode="after")
    def validate_review_reference(self) -> Self:
        if self.review.review_id != self.semantic.review_id:
            raise ValueError("review and semantic review_id must match")
        return self


class AnalystInput(Contract):
    product: Text
    goal: Text
    dimensions: UniqueDimensions
    report_language: Language
    reviews: Annotated[list[AnnotatedReview], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_reviews(self) -> Self:
        _unique([item.review.review_id for item in self.reviews])
        return self


class Insight(Contract):
    kind: Dimension
    title: ShortText
    summary: LongText
    evidence_ids: Annotated[
        list[Text],
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
        AfterValidator(_unique),
    ]
    hypothesis: Annotated[str, Field(max_length=1000)] | None


class AnalystOutput(Contract):
    summary: Annotated[str, Field(max_length=4000)]
    insights: Annotated[list[Insight], Field(max_length=20)]
    limitations: list[Annotated[str, Field(max_length=1000)]]


class MetricDescriptor(Contract):
    dataset: Dataset
    label_field: Literal["label"]
    value_field: Literal["count"]


class VisualizationInput(Contract):
    product: str
    report_language: Language
    available_metrics: list[MetricDescriptor]
    insight_titles: list[str]


class ChartSpec(Contract):
    chart: Literal["bar", "donut"]
    title: ShortText
    dataset: Dataset
    x: Literal["label"]
    y: Literal["count"]

    @model_validator(mode="after")
    def validate_topic_chart(self) -> Self:
        if self.dataset == "topic_distribution" and self.chart != "bar":
            raise ValueError("multi-label topic distribution requires a bar chart")
        return self


class VisualizationOutput(Contract):
    charts: Annotated[list[ChartSpec], Field(min_length=1, max_length=4)]
