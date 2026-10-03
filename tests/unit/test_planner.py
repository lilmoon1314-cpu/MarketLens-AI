"""Source authorization, contextual failure, and bounded deterministic fallback."""

import pytest

from marketlens.agents.planner import PlannerAgent
from marketlens.contracts import AnalysisRequest, PlannerInput, PlannerOutput


class StubLLM:
    def __init__(self, output):
        self.output = output
        self.payload = None

    def generate(self, schema, system, payload):
        self.payload = payload
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def data(sources=None, available=None, product="示例产品"):
    return PlannerInput(
        request=AnalysisRequest(
            product=product,
            goal="了解问题",
            sources=sources or ["local"],
            dataset_id="sample",
            product_urls=["https://item.taobao.com/item.htm?id=1"],
            max_reviews=1000,
            report_language="zh-CN",
        ),
        available_sources=available if available is not None else ["local"],
    )


def test_valid_planning_passes_and_limits_available_sources():
    output = PlannerOutput(sources=["local"], keywords=["电池"], dimensions=["pain_point"])
    llm = StubLLM(output)
    result = PlannerAgent(llm).plan(data(sources=["local", "taobao"], available=["local"]))
    assert result.plan == output
    assert result.warnings == []
    assert llm.payload.available_sources == ["local"]


@pytest.mark.parametrize(
    "output",
    [
        RuntimeError("private provider detail"),
        PlannerOutput(sources=["taobao"], keywords=["x"], dimensions=["pain_point"]),
    ],
)
def test_failure_or_unauthorized_source_uses_fallback(output):
    result = PlannerAgent(StubLLM(output)).plan(data(product="产" * 200))
    assert result.plan.sources == ["local"]
    assert result.plan.keywords == ["产" * 100]
    assert len(result.plan.dimensions) == 4
    assert result.warnings[0]["code"] == "planner_fallback"
    assert "private" not in repr(result.warnings)


def test_empty_intersection_does_not_invent_source():
    llm = StubLLM(RuntimeError())
    with pytest.raises(ValueError, match="no authorized"):
        PlannerAgent(llm).plan(data(available=[]))
    assert llm.payload is None
