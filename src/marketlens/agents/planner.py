"""Research planning with contextual source validation and deterministic fallback."""

from dataclasses import dataclass, field

from marketlens.adapters.llm import StructuredLLM
from marketlens.contracts import PlannerInput, PlannerOutput
from marketlens.prompts.planner import SYSTEM, VERSION


@dataclass
class PlanningResult:
    plan: PlannerOutput
    warnings: list[dict] = field(default_factory=list)


class PlannerAgent:
    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    def plan(self, data: PlannerInput) -> PlanningResult:
        allowed = [source for source in data.request.sources if source in data.available_sources]
        if not allowed:
            raise ValueError("no authorized available source")
        payload = PlannerInput(request=data.request, available_sources=allowed)
        try:
            output = self.llm.generate(PlannerOutput, SYSTEM, payload)
            output = PlannerOutput.model_validate(output.model_dump())
            if not set(output.sources) <= set(allowed):
                raise ValueError("source outside allowed intersection")
            return PlanningResult(output)
        except Exception:
            return PlanningResult(
                PlannerOutput(
                    sources=allowed,
                    keywords=[data.request.product[:100]],
                    dimensions=["strength", "weakness", "pain_point", "feature_request"],
                ),
                [
                    {
                        "code": "planner_fallback",
                        "stage": "planner",
                        "message": "规划失败或来源不合法，使用允许来源与默认维度",
                        "prompt_version": VERSION,
                    }
                ],
            )
