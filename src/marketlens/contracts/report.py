"""Final reports contain JSON values, computed counts, and fixed selected evidence."""

from typing import Annotated, Literal, Self

from pydantic import AfterValidator, JsonValue, model_validator

from .models import (
    AnalysisRequest,
    AnalystOutput,
    ChartSpec,
    Contract,
    Insight,
    PlannerOutput,
    Text,
    VisualizationOutput,
    _unique,
)
from .statistics import Count, Statistics

IDs = Annotated[list[Text], AfterValidator(_unique)]


class Selection(Contract):
    valid_count: Count
    strict_cap: Count
    candidate_ids: IDs
    selected_ids: IDs
    batches: list[IDs]
    batch_estimated_input_tokens: list[Count]
    estimated_run_tokens: Count
    token_count_method: Literal["estimated_utf8_bytes"]
    unselected_candidate_count: Count
    token_skipped_ids: IDs
    method: Literal["topic_stratified_largest_remainder"]
    threshold: float

    @model_validator(mode="after")
    def check_partition(self) -> Self:
        if (
            self.strict_cap != max(0, (3 * self.valid_count - 1) // 10)
            or len(self.selected_ids) > self.strict_cap
        ):
            raise ValueError("selection violates strict review cap")
        if not set(self.selected_ids) <= set(self.candidate_ids) or not set(
            self.token_skipped_ids
        ) <= set(self.candidate_ids) - set(self.selected_ids):
            raise ValueError("selection IDs outside candidate set")
        if [review_id for batch in self.batches for review_id in batch] != self.selected_ids:
            raise ValueError("batches must partition selection")
        if any(not batch or len(batch) > 20 for batch in self.batches) or len(self.batches) != len(
            self.batch_estimated_input_tokens
        ):
            raise ValueError("invalid batch metadata")
        if self.unselected_candidate_count != len(self.candidate_ids) - len(self.selected_ids):
            raise ValueError("candidate count mismatch")
        return self


class ReportInsight(Insight):
    insight_id: Text
    evidence_count: Count

    @model_validator(mode="after")
    def check_count(self) -> Self:
        if self.evidence_count != len(self.evidence_ids):
            raise ValueError("evidence count must equal unique references")
        return self


class ChartRow(Contract):
    label: Text
    count: Count


class BoundChart(ChartSpec):
    data: list[ChartRow]


class Notice(Contract):
    code: Text
    stage: Text
    message: Text
    prompt_version: Text | None = None
    retryable: bool | None = None


class AnalysisReport(Contract):
    schema_version: Literal["1.0"]
    run_id: Text
    status: Literal["complete", "partial", "insufficient_data", "failed"]
    mode: Literal["demo", "real"]
    request: AnalysisRequest
    plan: PlannerOutput | None
    review_count: Count
    raw_count: Count
    rejected_counts: dict[str, Count]
    selected_ids: IDs
    statistics: Statistics | None
    selection: Selection | None
    metrics: dict[str, JsonValue]
    analyst_result: AnalystOutput | None
    insights: list[ReportInsight]
    visualization: VisualizationOutput | None
    charts: list[BoundChart]
    warnings: list[Notice]
    errors: list[Notice]
    persisted: bool = False

    @model_validator(mode="after")
    def check_provenance(self) -> Self:
        if self.raw_count != self.review_count + sum(self.rejected_counts.values()):
            raise ValueError("report counts inconsistent")
        if (
            self.review_count
            and len(self.selected_ids) * 10 >= self.review_count * 3
            or not self.review_count
            and self.selected_ids
        ):
            raise ValueError("report selected ratio must be strictly below 30%")
        if self.selection is not None and (
            self.selection.valid_count != self.review_count
            or self.selection.selected_ids != self.selected_ids
        ):
            raise ValueError("report selection inconsistent")
        if self.statistics is not None and (
            self.statistics.valid_count != self.review_count
            or self.statistics.raw_count != self.raw_count
        ):
            raise ValueError("report statistics inconsistent")
        if any(
            not set(insight.evidence_ids) <= set(self.selected_ids) for insight in self.insights
        ):
            raise ValueError("report evidence outside selection")
        return self
