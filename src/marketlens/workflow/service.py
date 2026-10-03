"""Offline graph skeleton with isolated runtime dependencies and safe error messages."""

import json
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from marketlens.agents.analyst import AnalystAgent
from marketlens.agents.planner import PlannerAgent
from marketlens.agents.visualization import VisualizationAgent
from marketlens.contracts import (
    AnalysisReport,
    AnalysisRequest,
    AnalysisState,
    AnalystInput,
    AnalystOutput,
    AnnotatedReview,
    MetricDescriptor,
    PlannerInput,
    PlannerOutput,
    Review,
    SemanticReview,
    VisualizationInput,
    VisualizationOutput,
)
from marketlens.contracts.statistics import Statistics
from marketlens.storage.sqlite import RunStore
from marketlens.tools.charts import bind_charts, chart_datasets, default_charts, validate_charts
from marketlens.tools.collection import load_local_reviews
from marketlens.tools.evidence import insight_records
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
    analyst: AnalystAgent | None
    visualization: VisualizationAgent | None
    mode: str
    store: RunStore | None


def _initial(request: AnalysisRequest, mode: str = "demo") -> AnalysisState:
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
        metrics={"mode": mode},
        warnings=[{"code": "demo_mode", "stage": "start", "message": "模拟运行，非真实AI分析"}]
        if mode == "demo"
        else [],
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
    if runtime.context.analyst is not None:
        agent = runtime.context.analyst
        result = agent.analyze(data, state["selection"]["batches"])
        return {
            "analyst_result": result.output.model_dump(mode="json"),
            "warnings": [*state["warnings"], *result.warnings],
            "status": "partial" if result.warnings else state["status"],
            "metrics": {
                **state["metrics"],
                "analyst_mode": "real",
                "analyst_sent_ids": result.sent_ids,
                "llm": agent.llm.metrics(),
            },
        }
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
    backend = runtime.context.semantic
    metadata = getattr(backend, "cache_metadata", lambda: None)()
    if metadata:
        from marketlens.prompts.analyst import VERSION as analyst_version
        from marketlens.prompts.planner import VERSION as planner_version
        from marketlens.prompts.visualization import VERSION as visualization_version

        metadata = {
            **metadata,
            "language": state["request"]["report_language"],
            "prompts": [planner_version, analyst_version, visualization_version],
        }
    store = runtime.context.store
    hits = {}
    if store and store.enabled and metadata:
        try:
            for review in reviews:
                cached = store.cached(review.text, metadata, review.review_id)
                if cached is not None:
                    hits[review.review_id] = cached
        except sqlite3.Error:
            hits = {}  # Inference remains available when cache reading fails.
    misses = [review for review in reviews if review.review_id not in hits]
    fresh = backend.analyze(misses) if misses else []
    if len(fresh) != len(misses) or {a.review_id for a in fresh} != {
        review.review_id for review in misses
    }:
        raise ValueError("semantic review IDs mismatch")
    by_id = {**hits, **{a.review_id: a for a in fresh}}
    annotations = [by_id[review.review_id] for review in reviews]
    annotations = [SemanticReview.model_validate(item.model_dump()) for item in annotations]
    if len(annotations) != len(reviews) or {item.review_id for item in annotations} != {
        review.review_id for review in reviews
    }:
        raise ValueError("semantic review IDs mismatch")
    return {
        "annotations": [item.model_dump(mode="json") for item in annotations],
        "metrics": {
            **state["metrics"],
            "semantic_cache": metadata,
            "cache_hits": len(hits),
            "cache_misses": len(misses),
        },
    }


def _aggregate(state: AnalysisState, runtime: Runtime[Context]) -> dict:
    reviews = _reviews(state)
    annotations = [SemanticReview.model_validate(item) for item in state["annotations"]]
    statistics = aggregate_statistics(
        reviews, annotations, state["metrics"]["raw_count"], state["rejected_counts"]
    )
    budget = runtime.context.budget
    if (
        runtime.context.planner is not None
        or runtime.context.analyst is not None
        or runtime.context.visualization is not None
    ):
        llm = (
            runtime.context.planner or runtime.context.analyst or runtime.context.visualization
        ).llm
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
    datasets = _datasets(state)
    data = VisualizationInput(
        product=request.product,
        report_language=request.report_language,
        available_metrics=[
            MetricDescriptor(dataset=name, label_field="label", value_field="count")
            for name in datasets
        ],
        insight_titles=[item["label"] for item in datasets.get("insight_evidence_counts", [])],
    )
    if not datasets or state["errors"] or not state["analyst_result"]:
        output = default_charts(datasets)
        return {"visualization": output.model_dump(mode="json") if output else None}
    if runtime.context.visualization is not None:
        agent = runtime.context.visualization
        result = agent.configure(data)
        return {
            "visualization": result.output.model_dump(mode="json") if result.output else None,
            "warnings": [*state["warnings"], *result.warnings],
            "status": "partial" if result.warnings else state["status"],
            "metrics": {
                **state["metrics"],
                "llm": agent.llm.metrics(),
                "visualization_mode": "real",
            },
        }
    output = runtime.context.agents.visualization(data)
    output = VisualizationOutput.model_validate(output.model_dump())
    validate_charts(output, set(datasets))
    return {"visualization": output.model_dump(mode="json")}


def _datasets(state: AnalysisState) -> dict:
    if not state["statistics"]:
        return {}
    insights = (
        insight_records(AnalystOutput.model_validate(state["analyst_result"]).insights)
        if state["analyst_result"]
        else []
    )
    return chart_datasets(Statistics.model_validate(state["statistics"]), insights)


def _guard(name, node):
    def guarded(state: AnalysisState, runtime: Runtime[Context]) -> dict:
        try:
            update = {**node(state, runtime), "stage": name}
        except Exception:
            # Do not expose provider errors, paths, credentials, or review bodies to the report.
            update = {
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
        return _persist(state, update, runtime.context.store)

    return guarded


def _persist(state: AnalysisState, update: dict, store: RunStore | None) -> dict:
    if store is None or not store.enabled:
        return update
    snapshot = {**state, **update}
    if snapshot["report"] is not None:
        snapshot["report"] = {**snapshot["report"], "persisted": True}
        update["report"] = snapshot["report"]
    try:
        store.save_state(snapshot)
    except (sqlite3.Error, OSError):
        store.enabled = False
        warnings = [
            *snapshot["warnings"],
            {
                "code": "storage_failed",
                "stage": snapshot["stage"],
                "message": "存储不可用，结果仅保留在当前内存中，请导出报告",
            },
        ]
        update["warnings"] = warnings
        if snapshot["report"] is not None:
            update["report"] = {**snapshot["report"], "persisted": False, "warnings": warnings}
    return update


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
        "mode": state["metrics"]["mode"],
        "schema_version": state["schema_version"],
        "request": state["request"],
        "plan": state["plan"],
        "review_count": len(state["reviews"]),
        "raw_count": state["metrics"].get("raw_count", 0),
        "rejected_counts": state["rejected_counts"],
        "selected_ids": state["selected_ids"],
        "statistics": state["statistics"] or None,
        "selection": state["selection"] or None,
        "metrics": state["metrics"],
        "analyst_result": state["analyst_result"],
        "insights": insight_records(AnalystOutput.model_validate(state["analyst_result"]).insights)
        if state["analyst_result"]
        else [],
        "visualization": state["visualization"],
        "charts": bind_charts(
            VisualizationOutput.model_validate(state["visualization"])
            if state["visualization"]
            else None,
            _datasets(state),
        ),
        "warnings": state["warnings"],
        "errors": state["errors"],
    }
    report = AnalysisReport.model_validate_json(json.dumps(report)).model_dump(mode="json")
    return {"status": status, "stage": "finalize", "report": report}


def build_graph(checkpointer=None):
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
    graph.add_node("finalize", _guard("finalize", lambda state, runtime: _finalize(state)))
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", lambda s: "finalize" if s["errors"] else "collect")
    graph.add_conditional_edges(
        "collect", lambda s: "semantic" if not s["errors"] and s["reviews"] else "finalize"
    )
    graph.add_edge("semantic", "aggregate")
    graph.add_conditional_edges(
        "aggregate",
        lambda s: "analyst" if not s["errors"] and s["selected_ids"] else "visualization",
    )
    graph.add_edge("analyst", "visualization")
    graph.add_edge("visualization", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


class AnalysisService:
    """Shared graph for explicit demo, mixed component tests, and real analysis."""

    def __init__(
        self,
        datasets: Mapping[str, Path],
        agents: Agents,
        semantic: SemanticBackend | None = None,
        budget: RoutingBudget | None = None,
        planner: PlannerAgent | None = None,
        analyst: AnalystAgent | None = None,
        visualization: VisualizationAgent | None = None,
        mode: str = "demo",
        store: RunStore | None = None,
    ):
        from .demo import DemoSemantic

        active = [agent for agent in (planner, analyst, visualization) if agent is not None]
        if active and any(agent.llm is not active[0].llm for agent in active):
            raise ValueError("Agents must share one per-run LLM budget")
        if (
            mode not in {"demo", "real"}
            or mode == "real"
            and (len(active) != 3 or semantic is None)
        ):
            raise ValueError("real mode requires all real components")

        self.context = Context(
            dict(datasets),
            agents,
            semantic if semantic is not None else DemoSemantic(),
            budget or RoutingBudget(),
            planner,
            analyst,
            visualization,
            mode,
            store,
        )
        self.graph = build_graph()
        self._started = False

    def run(self, request: AnalysisRequest) -> dict:
        report = None
        for event in self.stream(request):
            report = event.get("report", report)
        if report is None:
            raise RuntimeError("workflow did not produce a report")
        return report

    @classmethod
    def real(cls, datasets: Mapping[str, Path], store: RunStore | None = None):
        from gliner2 import GLiNER2  # noqa: F401 - verify local inference dependency

        from marketlens.adapters.gliner import SemanticAnalyzer
        from marketlens.adapters.llm import StructuredLLM
        from marketlens.config import load_llm_config

        from .demo import DemoAgents

        llm = StructuredLLM(load_llm_config())
        return cls(
            datasets,
            DemoAgents(),
            SemanticAnalyzer(),
            planner=PlannerAgent(llm),
            analyst=AnalystAgent(llm),
            visualization=VisualizationAgent(llm),
            mode="real",
            store=store,
        )

    def stream(self, request: AnalysisRequest) -> Iterator[dict]:
        if self._started and any(
            (self.context.planner, self.context.analyst, self.context.visualization)
        ):
            raise ValueError("create a new service for each LLM run")
        self._started = True
        from contextlib import ExitStack

        from langgraph.checkpoint.sqlite import SqliteSaver

        state = _initial(request, self.context.mode)
        with ExitStack() as stack:
            graph = self.graph
            store = self.context.store
            if store and store.enabled:
                try:
                    saver = stack.enter_context(
                        SqliteSaver.from_conn_string(str(store.checkpoint_path))
                    )
                    saver.setup()
                    graph = build_graph(saver)
                except (sqlite3.Error, OSError):
                    state["warnings"].append(
                        {
                            "code": "checkpoint_unavailable",
                            "stage": "start",
                            "message": "工作流检查点不可用，继续内存分析",
                        }
                    )
            config = {"configurable": {"thread_id": state["run_id"]}}
            try:
                for current in graph.stream(
                    state, config=config, context=self.context, stream_mode="values"
                ):
                    state = current
                    yield self._event(state)
            except sqlite3.Error:
                # Never replay provider calls after a checkpoint write failure.
                state["warnings"] = [
                    *state["warnings"],
                    {
                        "code": "checkpoint_failed",
                        "stage": state["stage"],
                        "message": "检查点写入失败，保留已完成结果；未自动重试外部调用",
                    },
                ]
                state["status"] = "partial" if state["reviews"] else "failed"
                state["report"] = None
                state.update(_persist(state, _finalize(state), store))
                yield self._event(state)

    def _event(self, state: AnalysisState) -> dict:
        self.last_state = state
        event = {
            "run_id": state["run_id"],
            "stage": state["stage"],
            "status": state["status"],
            "message": ("模拟运行：" if self.context.mode == "demo" else "分析进度：")
            + state["stage"],
        }
        if state["report"] is not None:
            event["report"] = state["report"]
        return event
