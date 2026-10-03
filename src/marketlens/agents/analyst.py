"""Budget-refined batches, partial recovery, and evidence-constrained merge."""

from dataclasses import dataclass

from marketlens.adapters.llm import StructuredLLM
from marketlens.contracts import AnalystInput, AnalystOutput
from marketlens.prompts.analyst import MERGE_SYSTEM, SYSTEM
from marketlens.tools.evidence import insight_records, merge_duplicates, validate_insights


@dataclass
class AnalysisResult:
    output: AnalystOutput
    warnings: list[dict]
    sent_ids: list[str]
    insights: list[dict]


class AnalystAgent:
    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    def analyze(self, data: AnalystInput, batches: list[list[str]]) -> AnalysisResult:
        by_id = {item.review.review_id: item for item in data.reviews}
        flat = [review_id for batch in batches for review_id in batch]
        if len(set(flat)) != len(flat) or set(flat) != set(by_id):
            raise ValueError("batch IDs must partition the fixed selection")
        refined: list[AnalystInput] = []
        warnings: list[dict] = []
        for batch in batches:
            current = []
            for review_id in batch:
                item = by_id[review_id]
                proposal = data.model_copy(update={"reviews": [*current, item]})
                if (
                    len(current) >= 20
                    or self.llm.estimate_input(AnalystOutput, SYSTEM, proposal)
                    > self.llm.config.effective_input_tokens
                ):
                    if current:
                        refined.append(data.model_copy(update={"reviews": current}))
                    current = []
                    proposal = data.model_copy(update={"reviews": [item]})
                if (
                    self.llm.estimate_input(AnalystOutput, SYSTEM, proposal)
                    > self.llm.config.effective_input_tokens
                ):
                    warnings.append(
                        self._warning("analyst_long_review", "完整评论超出上下文，未送入LLM")
                    )
                    continue
                current.append(item)
            if current:
                refined.append(data.model_copy(update={"reviews": current}))
        outputs = []
        sent: set[str] = set()
        for batch in refined:
            before = len(self.llm.calls)
            try:
                result = self.llm.generate(AnalystOutput, SYSTEM, batch)
                result, issues = validate_insights(
                    result, {item.review.review_id for item in batch.reviews}
                )
                warnings.extend(issues)
                outputs.append(result)
            except Exception:
                warnings.append(
                    self._warning("analyst_batch_failed", "批次失败或预算不足，保留其他有效结果")
                )
            finally:
                if len(self.llm.calls) > before:
                    sent.update(item.review.review_id for item in batch.reviews)
        merged = merge_duplicates([insight for output in outputs for insight in output.insights])
        final = AnalystOutput(
            summary=f"根据已分析样本保留{len(merged)}条有证据的洞察，不代表总体发生率。",
            insights=merged,
            limitations=["洞察来自预算内抽样，不能外推总体频率。"],
        )
        if len(outputs) > 1 and merged:
            try:
                merged_output = self.llm.generate(
                    AnalystOutput,
                    MERGE_SYSTEM,
                    {
                        "product": data.product,
                        "goal": data.goal,
                        "report_language": data.report_language,
                        "insights": [insight.model_dump(mode="json") for insight in merged],
                    },
                )
                final, issues = validate_insights(
                    merged_output,
                    {review_id for insight in merged for review_id in insight.evidence_ids},
                )
                warnings.extend(issues)
                final = final.model_copy(update={"insights": merge_duplicates(final.insights)})
            except Exception:
                warnings.append(
                    self._warning(
                        "analyst_merge_fallback", "合并失败或预算不足，使用确定性去重结果"
                    )
                )
        elif len(outputs) == 1 and not warnings:
            final = outputs[0].model_copy(update={"insights": merged})
        return AnalysisResult(final, warnings, sorted(sent), insight_records(final.insights))

    @staticmethod
    def _warning(code: str, message: str) -> dict:
        return {"code": code, "stage": "analyst", "message": message}
