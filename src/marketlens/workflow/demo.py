"""Explicit offline fixtures: these outputs do not evaluate AI quality."""

from marketlens.adapters.gliner import convert
from marketlens.contracts import (
    AnalystInput,
    AnalystOutput,
    Insight,
    PlannerInput,
    PlannerOutput,
    VisualizationInput,
    VisualizationOutput,
)


class DemoSemantic:
    """Fixed semantic fixture; no model quality claim."""

    def cache_metadata(self) -> dict:
        return {"model": "demo", "revision": "1.0"}

    def analyze(self, reviews):
        return [
            convert(
                review.review_id,
                {
                    "sentiment": {"label": "positive", "confidence": 1.0},
                    "topics": [{"label": "quality", "confidence": 1.0}],
                    "feedback_value": {"label": "actionable", "confidence": 1.0},
                },
                False,
            )
            for review in reviews
        ]


class DemoAgents:
    def planner(self, data: PlannerInput) -> PlannerOutput:
        return PlannerOutput(
            sources=[source for source in data.request.sources if source in data.available_sources],
            keywords=[data.request.product],
            dimensions=["strength", "weakness", "pain_point", "feature_request"],
        )

    def analyst(self, data: AnalystInput) -> AnalystOutput:
        return AnalystOutput(
            summary="模拟工作流已完成；以下仅验证数据与证据传递。",
            insights=[
                Insight(
                    kind="pain_point",
                    title="模拟洞察",
                    summary="展示一条样例评论作为证据。",
                    evidence_ids=[data.reviews[0].review.review_id],
                    hypothesis=None,
                )
            ],
            limitations=["未运行真实语义模型或LLM，不可作为产品决策依据。"],
        )

    def visualization(self, data: VisualizationInput) -> VisualizationOutput:
        return VisualizationOutput.model_validate(
            {
                "charts": [
                    {
                        "chart": "bar",
                        "title": "模拟反馈分布",
                        "dataset": data.available_metrics[0].dataset,
                        "x": "label",
                        "y": "count",
                    }
                ]
            }
        )
