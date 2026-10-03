"""Server-owned chart data: models select configs, never numbers or rendering code."""

from marketlens.contracts import VisualizationOutput
from marketlens.contracts.statistics import Statistics

TITLES = {
    "sentiment_distribution": "情绪分布",
    "topic_distribution": "评论主题",
    "feedback_value_distribution": "反馈价值",
    "insight_evidence_counts": "洞察证据数量",
}
LABELS = {
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "mixed": "褒贬混合",
    "unknown": "未知",
    "actionable": "具体反馈",
    "non_actionable": "笼统评价",
    "spam": "广告推广",
    "pricing": "价格",
    "performance": "性能",
    "reliability": "可靠性",
    "usability": "易用性",
    "features": "功能",
    "support": "服务",
    "quality": "质量",
    "delivery": "物流",
    "packaging": "包装",
    "other": "其他",
}


def chart_datasets(statistics: Statistics, insights: list[dict]) -> dict[str, list[dict]]:
    result = {}
    for name in ("sentiment_distribution", "topic_distribution", "feedback_value_distribution"):
        counts = getattr(statistics, name)
        if sum(counts.values()):
            result[name] = [{"label": LABELS[key], "count": count} for key, count in counts.items()]
    if insights:
        result["insight_evidence_counts"] = [
            {"label": item["title"], "count": item["evidence_count"]} for item in insights
        ]
    return result


def default_charts(datasets: dict) -> VisualizationOutput | None:
    if not datasets:
        return None
    return VisualizationOutput.model_validate(
        {
            "charts": [
                {"chart": "bar", "title": TITLES[name], "dataset": name, "x": "label", "y": "count"}
                for name in TITLES
                if name in datasets
            ]
        }
    )


def validate_charts(output: VisualizationOutput, available: set[str]) -> None:
    names = [chart.dataset for chart in output.charts]
    if not set(names) <= available or len(set(names)) != len(names):
        raise ValueError("charts must reference unique available datasets")


def bind_charts(output: VisualizationOutput | None, datasets: dict) -> list[dict]:
    if output is None:
        return []
    validate_charts(output, set(datasets))
    return [
        {**chart.model_dump(mode="json"), "data": datasets[chart.dataset]}
        for chart in output.charts
    ]
