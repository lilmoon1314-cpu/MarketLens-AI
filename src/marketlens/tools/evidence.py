"""Contextual evidence validation and program-computed insight identifiers/counts."""

import json
import unicodedata
from hashlib import sha256

from marketlens.contracts import AnalystOutput, Insight


def validate_insights(
    output: AnalystOutput, allowed_ids: set[str]
) -> tuple[AnalystOutput, list[dict]]:
    valid = [insight for insight in output.insights if set(insight.evidence_ids) <= allowed_ids]
    rejected = len(output.insights) - len(valid)
    if not rejected and valid:
        return output, []
    return AnalystOutput(
        summary=f"证据校验后保留{len(valid)}条洞察，摘要仅依据有效引用重建。",
        insights=valid,
        limitations=[
            *output.limitations,
            *(["部分洞察引用不属于本批评论，已移除。"] if rejected else []),
        ],
    ), (
        [{"code": "invalid_evidence", "stage": "analyst", "message": "已移除含非法证据引用的洞察"}]
        if rejected
        else []
    )


def merge_duplicates(insights: list[Insight]) -> list[Insight]:
    groups: dict[tuple[str, str], Insight] = {}
    for insight in sorted(
        insights, key=lambda item: (item.kind, item.title, sorted(item.evidence_ids))
    ):
        key = (
            insight.kind,
            " ".join(unicodedata.normalize("NFKC", insight.title).casefold().split()),
        )
        if key in groups:
            first = groups[key]
            groups[key] = first.model_copy(
                update={"evidence_ids": sorted(set(first.evidence_ids) | set(insight.evidence_ids))}
            )
        else:
            groups[key] = insight.model_copy(update={"evidence_ids": sorted(insight.evidence_ids)})
    return sorted(
        groups.values(), key=lambda item: (-len(item.evidence_ids), item.kind, item.title)
    )[:20]


def insight_records(insights: list[Insight]) -> list[dict]:
    records = []
    for insight in merge_duplicates(insights):
        identity = json.dumps(
            [insight.kind, insight.title, sorted(insight.evidence_ids)], ensure_ascii=False
        )
        records.append(
            {
                **insight.model_dump(mode="json"),
                "insight_id": sha256(identity.encode()).hexdigest(),
                "evidence_count": len(set(insight.evidence_ids)),
            }
        )
    return records
