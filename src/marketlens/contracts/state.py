"""Serializable LangGraph state declaration; graph execution is introduced in F03."""

from typing import Literal, TypedDict

type JSONObject = dict[str, object]
type RunStatus = Literal["running", "complete", "partial", "insufficient_data", "failed"]


class AnalysisState(TypedDict):
    schema_version: str
    run_id: str
    status: RunStatus
    stage: str
    request: JSONObject
    plan: JSONObject | None
    reviews: list[JSONObject]
    rejected_counts: dict[str, int]
    annotations: list[JSONObject]
    candidate_ids: list[str]
    selected_ids: list[str]
    selection: JSONObject
    statistics: JSONObject
    analyst_result: JSONObject | None
    visualization: JSONObject | None
    report: JSONObject | None
    metrics: JSONObject
    warnings: list[JSONObject]
    errors: list[JSONObject]
