"""Explicit real Chinese inference; default CI does not load NLP dependencies."""

import pytest

from marketlens.adapters.gliner import GLiNERConfig, SemanticAnalyzer, local_backend
from marketlens.tools.collection import normalize_reviews


@pytest.mark.model_smoke
def test_real_chinese_model_and_truncation():
    backend = local_backend(GLiNERConfig())
    assert backend is local_backend(GLiNERConfig())
    reviews = normalize_reviews(
        [
            {"text": "电池续航只有两小时，希望改进。"},
            {"text": "包装完整，物流很快，操作也很方便。"},
            {"text": "续航只有两小时。" * 300},
        ]
    ).reviews
    results = SemanticAnalyzer(backend=backend).analyze(reviews)
    assert all(result.processed for result in results)
    assert all(result.confidence.sentiment is not None for result in results)
    assert results[-1].truncated
    assert not results[0].truncated
    assert len(reviews[-1].text) > 1000


@pytest.mark.model_smoke
def test_real_semantic_graph_with_demo_agents(tmp_path):
    from marketlens.contracts import AnalysisRequest
    from marketlens.workflow.demo import DemoAgents
    from marketlens.workflow.service import AnalysisService

    path = tmp_path / "reviews.csv"
    path.write_text(
        "text\n电池续航只有两小时，希望改进。\n包装完整，物流很快，操作也很方便。\n不错。\n操作需要五个步骤，希望简化。\n",
        encoding="utf-8",
    )
    request = AnalysisRequest(
        product="示例",
        goal="了解反馈",
        sources=["local"],
        dataset_id="sample",
        product_urls=[],
        max_reviews=1000,
        report_language="zh-CN",
    )
    report = AnalysisService({"sample": path}, DemoAgents(), SemanticAnalyzer()).run(request)
    assert report["statistics"]["annotated_count"] == 4
    assert len(report["selected_ids"]) < 0.3 * report["review_count"]
    assert report["mode"] == "demo"  # real semantic model, fake LLM agents
