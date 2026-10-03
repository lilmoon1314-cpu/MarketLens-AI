"""Chart config whitelists and server-owned data; no renderer or LLM network."""

import pytest

from marketlens.agents.visualization import VisualizationAgent
from marketlens.contracts import MetricDescriptor, VisualizationInput, VisualizationOutput
from marketlens.tools.charts import bind_charts, chart_datasets, default_charts
from marketlens.tools.collection import normalize_reviews
from marketlens.tools.statistics import aggregate_statistics


class Stub:
    def __init__(self, output):
        self.output = output
        self.payload = None

    def generate(self, schema, system, payload):
        self.payload = payload
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def data(names=("sentiment_distribution", "topic_distribution")):
    return VisualizationInput(
        product="示例",
        report_language="zh-CN",
        insight_titles=[],
        available_metrics=[
            MetricDescriptor(dataset=name, label_field="label", value_field="count")
            for name in names
        ],
    )


def output(dataset="sentiment_distribution", chart="bar"):
    return VisualizationOutput.model_validate(
        {
            "charts": [
                {"chart": chart, "title": "分布", "dataset": dataset, "x": "label", "y": "count"}
            ]
        }
    )


def test_valid_choice_has_no_review_bodies_or_numbers():
    stub = Stub(output(chart="donut"))
    result = VisualizationAgent(stub).configure(data())
    assert result.warnings == []
    assert result.output.charts[0].chart == "donut"
    assert set(stub.payload.model_dump()) == {
        "product",
        "report_language",
        "available_metrics",
        "insight_titles",
    }


@pytest.mark.parametrize(
    "bad",
    [
        RuntimeError("private provider detail"),
        output(dataset="feedback_value_distribution"),
        VisualizationOutput(charts=[output().charts[0], output().charts[0]]),
    ],
)
def test_failure_unavailable_or_duplicate_dataset_fallback(bad):
    result = VisualizationAgent(Stub(bad)).configure(data())
    assert {c.dataset for c in result.output.charts} == {
        "sentiment_distribution",
        "topic_distribution",
    }
    assert all(c.chart == "bar" for c in result.output.charts)
    assert result.warnings[0]["code"] == "visualization_fallback"
    assert "private" not in repr(result.warnings)


@pytest.mark.parametrize("dataset", ["topic_distribution", "insight_evidence_counts"])
def test_overlapping_counts_forbid_donut(dataset):
    with pytest.raises(ValueError):
        output(dataset=dataset, chart="donut")


def test_no_data_skips_llm_and_zero_counts_omit_datasets():
    stub = Stub(RuntimeError())
    assert VisualizationAgent(stub).configure(data(())).output is None
    assert stub.payload is None
    assert chart_datasets(aggregate_statistics([], [], 0, {}), []) == {}
    assert default_charts({}) is None


def test_chinese_server_data_binding_and_unknown_partition():
    reviews = normalize_reviews([{"text": "有效评论"}]).reviews
    statistics = aggregate_statistics(reviews, [], 1, {})
    datasets = chart_datasets(statistics, [{"title": "示例问题", "evidence_count": 1}])
    assert len(datasets) == 4
    assert {row["label"]: row["count"] for row in datasets["sentiment_distribution"]}["未知"] == 1
    charts = bind_charts(default_charts(datasets), datasets)
    assert len(charts) == 4
    assert all(chart["y"] == "count" for chart in charts)
    assert charts[-1]["data"] == [{"label": "示例问题", "count": 1}]
    with pytest.raises(ValueError, match="available"):
        bind_charts(output(dataset="topic_distribution"), {})
