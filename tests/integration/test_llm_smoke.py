"""Explicit minimal real provider request using configured credentials."""

import json
import os
from pathlib import Path

import pytest

from marketlens.adapters.llm import StructuredLLM
from marketlens.config import load_llm_config
from marketlens.contracts import PlannerOutput


@pytest.mark.live_api
def test_live_structured_output():
    config = load_llm_config(Path(os.environ.get("MARKETLENS_ENV_FILE", ".env")))
    llm = StructuredLLM(config)
    result = llm.generate(
        PlannerOutput,
        "按输入返回规划。来源只用local，维度只用pain_point。",
        {
            "product": "开发验证样例",
            "sources": ["local"],
            "dimensions": ["pain_point"],
        },
    )
    assert result.sources == ["local"]
    assert result.dimensions == ["pain_point"]
    assert llm.calls[-1]["status"] == "complete"
    assert len(llm.calls) <= 2


@pytest.mark.live_api
def test_live_research_planner():
    from marketlens.agents.planner import PlannerAgent
    from marketlens.contracts import AnalysisRequest, PlannerInput

    llm = StructuredLLM(load_llm_config(Path(os.environ.get("MARKETLENS_ENV_FILE", ".env"))))
    request = AnalysisRequest(
        product="示例蓝牙耳机",
        goal="了解续航和操作问题",
        sources=["local"],
        dataset_id="sample",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )
    result = PlannerAgent(llm).plan(PlannerInput(request=request, available_sources=["local"]))
    assert result.warnings == []
    assert result.plan.sources == ["local"]
    assert result.plan.keywords


@pytest.mark.live_api
def test_live_review_analyst():
    from marketlens.agents.analyst import AnalystAgent
    from marketlens.contracts import AnalystInput, AnnotatedReview
    from marketlens.tools.collection import normalize_reviews
    from marketlens.tools.routing import select_reviews
    from marketlens.workflow.demo import DemoSemantic

    reviews = normalize_reviews(
        [
            {"text": "电池续航只有两小时，希望改进。"},
            {"text": "电池两小时就没电，出门需要频繁充电。"},
        ]
        + [{"text": f"普通评分，样例{i}"} for i in range(8)]
    ).reviews
    annotations = DemoSemantic().analyze(reviews)
    for item in annotations[2:]:
        item.feedback_value = "non_actionable"
    selection = select_reviews(reviews, annotations)
    assert len(selection["selected_ids"]) * 10 < len(reviews) * 3
    data = AnalystInput(
        product="示例耳机",
        goal="了解续航问题",
        dimensions=["pain_point"],
        report_language="zh-CN",
        reviews=[
            AnnotatedReview(review=r, semantic=s)
            for r, s in zip(reviews, annotations, strict=True)
            if r.review_id in selection["selected_ids"]
        ],
    )
    llm = StructuredLLM(load_llm_config(Path(os.environ.get("MARKETLENS_ENV_FILE", ".env"))))
    result = AnalystAgent(llm).analyze(data, selection["batches"])
    assert result.warnings == []
    assert result.insights
    assert all(
        set(item["evidence_ids"]) <= {r.review_id for r in reviews} for item in result.insights
    )
    assert all(item["evidence_count"] == len(set(item["evidence_ids"])) for item in result.insights)


@pytest.mark.live_api
def test_live_visualization_agent():
    from marketlens.agents.visualization import VisualizationAgent
    from marketlens.contracts import MetricDescriptor, VisualizationInput

    llm = StructuredLLM(load_llm_config(Path(os.environ.get("MARKETLENS_ENV_FILE", ".env"))))
    result = VisualizationAgent(llm).configure(
        VisualizationInput(
            product="示例",
            report_language="zh-CN",
            insight_titles=["电池续航短"],
            available_metrics=[
                MetricDescriptor(
                    dataset="topic_distribution", label_field="label", value_field="count"
                )
            ],
        )
    )
    assert result.warnings == []
    assert result.output.charts[0].dataset == "topic_distribution"
    assert result.output.charts[0].chart == "bar"


@pytest.mark.live_api
@pytest.mark.model_smoke
def test_real_local_pipeline(tmp_path):
    from marketlens.contracts import AnalysisRequest
    from marketlens.workflow.service import AnalysisService

    path = tmp_path / "reviews.jsonl"
    path.write_text(
        "".join(
            json.dumps({"text": f"包装完整，物流很快，操作也很方便。样例{i}"}) + "\n"
            for i in range(12)
        ),
        encoding="utf-8",
    )
    request = AnalysisRequest(
        product="开发验证样例商品",
        goal="了解操作与包装反馈",
        sources=["local"],
        dataset_id="sample",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )
    report = AnalysisService.real({"sample": path}).run(request)
    assert report["mode"] == "real"
    assert report["status"] in {"complete", "partial"}
    assert report["statistics"]["annotated_count"] == 12
    assert len(report["selected_ids"]) * 10 < report["review_count"] * 3
    assert report["charts"]
    assert report["metrics"]["llm"]["charged_tokens"] > 0
    assert all(
        set(item["evidence_ids"]) <= set(report["selected_ids"]) for item in report["insights"]
    )
