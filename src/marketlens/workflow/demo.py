"""Explicit offline fixtures: these outputs do not evaluate AI quality."""

from marketlens.contracts import (
    AnalystInput,
    AnalystOutput,
    Insight,
    PlannerInput,
    PlannerOutput,
    VisualizationInput,
    VisualizationOutput,
)


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
                        "title": "模拟证据数量",
                        "dataset": "insight_evidence_counts",
                        "x": "label",
                        "y": "count",
                    }
                ]
            }
        )
