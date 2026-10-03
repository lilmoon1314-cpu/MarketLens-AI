"""Bounded chart configuration with deterministic data-aware fallback."""

from dataclasses import dataclass

from marketlens.adapters.llm import StructuredLLM
from marketlens.contracts import VisualizationInput, VisualizationOutput
from marketlens.prompts.visualization import SYSTEM
from marketlens.tools.charts import default_charts, validate_charts


@dataclass
class VisualizationResult:
    output: VisualizationOutput | None
    warnings: list[dict]


class VisualizationAgent:
    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    def configure(self, data: VisualizationInput) -> VisualizationResult:
        available = {metric.dataset for metric in data.available_metrics}
        if not available:
            return VisualizationResult(None, [])
        try:
            output = self.llm.generate(VisualizationOutput, SYSTEM, data)
            output = VisualizationOutput.model_validate(output.model_dump())
            validate_charts(output, available)
            return VisualizationResult(output, [])
        except Exception:
            return VisualizationResult(
                default_charts(dict.fromkeys(available)),
                [
                    {
                        "code": "visualization_fallback",
                        "stage": "visualization",
                        "message": "图表配置失败或不合法，使用已有数据的默认柱状图",
                    },
                ],
            )
