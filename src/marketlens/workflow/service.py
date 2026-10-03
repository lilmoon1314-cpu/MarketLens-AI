"""Offline graph skeleton with isolated runtime dependencies and safe error messages."""

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from marketlens.agents.planner import PlannerAgent
from marketlens.contracts import (
    AnalysisRequest,
    AnalysisState,
    AnalystInput,
    AnalystOutput,
    AnnotatedReview,
    PlannerInput,
    PlannerOutput,
    Review,
    SemanticReview,
    VisualizationInput,
    VisualizationOutput,
)
from marketlens.tools.collection import load_local_reviews
from marketlens.tools.routing import RoutingBudget, select_reviews, selected_evidence
from marketlens.tools.statistics import aggregate_statistics


class Agents(Protocol):
    def planner(self, data: PlannerInput) -> PlannerOutput: ...
    def analyst(self, data: AnalystInput) -> AnalystOutput: ...
    def visualization(self, data: VisualizationInput) -> VisualizationOutput: ...


class SemanticBackend(Protocol):
    def analyze(self, reviews: list[Review]) -> list[SemanticReview]: ...


@dataclass(frozen=True)
class Context:
    datasets: Mapping[str, Path]
    agents: Agents
    semantic: SemanticBackend
    budget: RoutingBudget
    planner: PlannerAgent | None


def _initial(request: AnalysisRequest) -> AnalysisState:
    return AnalysisState(
        schema_version="1.0",
        run_id=str(uuid4()),
        status="running",
        stage="start",
        request=request.model_dump(mode="json"),
        plan=None,
        reviews=[],
        rejected_counts={},
        annotations=[],
        candidate_ids=[],
        selected_ids=[],
        selection={},
        statistics={},
        analyst_result=None,
        visualization=None,
        report=None,
        metrics={"mode": "demo"},
        warnings=[{"code": "demo_mode", "stage": "start", "message": "模拟运行，非真实AI分析"}],
        errors=[],
    )


def _planner(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    request = AnalysisRequest.model_validate(state["request"])
    data = PlannerInput(request=request, available_sources=["local"])
    warning = []
    metrics = state["metrics"]
    if runtime.context.planner is not None:
        result = runtime.context.planner.plan(data)
        plan, warning = result.plan, result.warnings
        metrics = {**metrics, "llm": runtime.context.planner.llm.metrics(), "planner_mode": "real"}
    else:
        plan = runtime.context.agents.planner(data)
    plan = PlannerOutput.model_validate(plan.model_dump())
    if any(source not in request.sources or source != "local" for source in plan.sources):
        raise ValueError("unavailable source")
    return {
        "plan": plan.model_dump(mode="json"),
        "warnings": [*state["warnings"], *warning],
        "metrics": metrics,
        "status": "partial" if warning else state["status"],
    }


def _collect(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    request = AnalysisRequest.model_validate(state["request"])
    result = load_local_reviews(request.dataset_id, runtime.context.datasets, request.max_reviews)
    return {
        "reviews": [review.model_dump(mode="json") for review in result.reviews],
        "rejected_counts": result.rejected_counts,
        "metrics": {**state["metrics"], "raw_count": result.raw_count},
    }


def _analyst(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    request = AnalysisRequest.model_validate(state["request"])
    reviews = selected_evidence(_reviews(state), state["selected_ids"], state["selected_ids"])
    annotations = {
        item["review_id"]: SemanticReview.model_validate(item) for item in state["annotations"]
    }
    data = AnalystInput(
        product=request.product,
        goal=request.goal,
        report_language=request.report_language,
        dimensions=state["plan"]["dimensions"],
        reviews=[
            AnnotatedReview(review=review, semantic=annotations[review.review_id])
            for review in reviews
        ],
    )
    output = runtime.context.agents.analyst(data)
    output = AnalystOutput.model_validate(output.model_dump())
    if any(
        evidence not in state["selected_ids"]
        for insight in output.insights
        for evidence in insight.evidence_ids
    ):
        raise ValueError("invalid evidence")
    return {"analyst_result": output.model_dump(mode="json")}


def _reviews(state: AnalysisState) -> list[Review]:
    return [Review.model_validate_json(json.dumps(item)) for item in state["reviews"]]


def _semantic(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    reviews = _reviews(state)
    annotations = runtime.context.semantic.analyze(reviews)
    annotations = [SemanticReview.model_validate(item.model_dump()) for item in annotations]
    if len(annotations) != len(reviews) or {item.review_id for item in annotations} != {
        review.review_id for review in reviews
    }:
        raise ValueError("semantic review IDs mismatch")
    return {"annotations": [item.model_dump(mode="json") for item in annotations]}


def _aggregate(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    reviews = _reviews(state)
    annotations = [SemanticReview.model_validate(item) for item in state["annotations"]]
    statistics = aggregate_statistics(
        reviews, annotations, state["metrics"]["raw_count"], state["rejected_counts"]
    )
    budget = runtime.context.budget
    if runtime.context.planner is not None:
        llm = runtime.context.planner.llm
        budget = replace(
            budget,
            remaining_run_tokens=min(budget.remaining_run_tokens, llm.remaining_tokens),
            input_tokens=min(budget.input_tokens, llm.config.effective_input_tokens),
            output_tokens=llm.config.output_tokens,
        )
    selection = select_reviews(reviews, annotations, budget)
    return {
        "statistics": statistics.model_dump(mode="json"),
        "selection": selection,
        "candidate_ids": selection["candidate_ids"],
        "selected_ids": selection["selected_ids"],
    }


def _visualization(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    request = AnalysisRequest.model_validate(state["request"])
    output = runtime.context.agents.visualization(
        VisualizationInput(
            product=request.product,
            report_language=request.report_language,
            available_metrics=[],
            insight_titles=[i["title"] for i in state["analyst_result"]["insights"]],
        )
    )
    output = VisualizationOutput.model_validate(output.model_dump())
    return {"visualization": output.model_dump(mode="json")}


def _guard(name, node):
    def guarded(state: AnalysisState, runtime: Runtime[Context]) -> dict:
        try:
            return {**node(state, runtime), "stage": name}
        except Exception:
            # Do not expose provider errors, paths, credentials, or review bodies to the report.
            return {
                "stage": name,
                "status": "partial" if state["reviews"] else "failed",
                "errors": [
                    *state["errors"],
                    {
                        "code": "node_failed",
                        "stage": name,
                        "retryable": False,
                        "message": "节点执行失败，已保留可用结果",
                    },
                ],
            }

    return guarded


def _finalize(state: AnalysisState) -> dict:
    status = state["status"]
    if status == "running":
        if not state["reviews"]:
            status = "insufficient_data"
        elif (
            not state["selected_ids"]
            or state["rejected_counts"]
            or state["statistics"].get("unprocessed_count", 0)
        ):
            status = "partial"
        else:
            status = "complete"
    report = {
        "run_id": state["run_id"],
        "status": status,
        "mode": "demo",
        "review_count": len(state["reviews"]),
        "raw_count": state["metrics"].get("raw_count", 0),
        "rejected_counts": state["rejected_counts"],
        "selected_ids": state["selected_ids"],
        "statistics": state["statistics"],
        "selection": state["selection"],
        "metrics": state["metrics"],
        "analyst_result": state["analyst_result"],
        "visualization": state["visualization"],
        "warnings": state["warnings"],
        "errors": state["errors"],
    }
    return {"status": status, "stage": "finalize", "report": report}


def build_graph():
    graph = StateGraph(AnalysisState, context_schema=Context)
    for name, node in [
        ("planner", _planner),
        ("collect", _collect),
        ("semantic", _semantic),
        ("aggregate", _aggregate),
        ("analyst", _analyst),
        ("visualization", _visualization),
    ]:
        graph.add_node(name, _guard(name, node))
    graph.add_node("finalize", _finalize)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", lambda s: "finalize" if s["errors"] else "collect")
    graph.add_conditional_edges(
        "collect", lambda s: "semantic" if not s["errors"] and s["reviews"] else "finalize"
    )
    graph.add_edge("semantic", "aggregate")
    graph.add_conditional_edges(
        "aggregate", lambda s: "analyst" if not s["errors"] and s["selected_ids"] else "finalize"
    )
    graph.add_conditional_edges("analyst", lambda s: "finalize" if s["errors"] else "visualization")
    graph.add_edge("visualization", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


class AnalysisService:
    """Explicit demo service; shared graph for run and progress streaming."""

    def __init__(
        self,
        datasets: Mapping[str, Path],
        agents: Agents,
        semantic: SemanticBackend | None = None,
        budget: RoutingBudget | None = None,
        planner: PlannerAgent | None = None,
    ):
        from .demo import DemoSemantic

        self.context = Context(
            dict(datasets),
            agents,
            semantic if semantic is not None else DemoSemantic(),
            budget or RoutingBudget(),
            planner,
        )
        self.graph = build_graph()

    def run(self, request: AnalysisRequest) -> dict:
        return self.graph.invoke(_initial(request), context=self.context)["report"]

    def stream(self, request: AnalysisRequest) -> Iterator[dict]:
        for state in self.graph.stream(
            _initial(request), context=self.context, stream_mode="values"
        ):
            event = {
                "run_id": state["run_id"],
                "stage": state["stage"],
                "status": state["status"],
                "message": "模拟运行：" + state["stage"],
            }
            if state["report"] is not None:
                event["report"] = state["report"]
            yield event
