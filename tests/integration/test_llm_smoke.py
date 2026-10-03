"""Explicit minimal real provider request using configured credentials."""

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
