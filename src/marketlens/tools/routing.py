"""Deterministic topic-stratified sampling and complete-comment input budgets."""

import json
from collections import defaultdict
from dataclasses import dataclass

from marketlens.adapters.gliner import TOPICS
from marketlens.contracts import Review, SemanticReview


@dataclass(frozen=True)
class RoutingBudget:
    input_tokens: int = 8000
    reserved_input_tokens: int = 2000
    output_tokens: int = 2000
    remaining_run_tokens: int = 60000
    batch_reviews: int = 20

    def __post_init__(self):
        if (
            any(
                type(value) is not int or value < 0
                for value in (
                    self.input_tokens,
                    self.reserved_input_tokens,
                    self.output_tokens,
                    self.remaining_run_tokens,
                )
            )
            or type(self.batch_reviews) is not int
            or not 1 <= self.batch_reviews <= 20
        ):
            raise ValueError("invalid token or batch budget")


def strict_review_cap(valid_count: int) -> int:
    if type(valid_count) is not int or valid_count < 0:
        raise ValueError("valid_count must be a nonnegative integer")
    return max(0, (3 * valid_count - 1) // 10)


def _topic(annotation: SemanticReview) -> str:
    topics = [topic for topic in TOPICS if topic in annotation.topics]
    return (
        max(topics, key=lambda topic: annotation.confidence.topics.get(topic, -1))
        if topics
        else "other"
    )


def _cost(review: Review, annotation: SemanticReview) -> int:
    # Conservative UTF-8 byte estimate for BPE providers; actual usage is accounted in F07.
    return len(
        json.dumps(
            {
                "review": review.model_dump(mode="json"),
                "semantic": annotation.model_dump(mode="json"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def select_reviews(
    reviews: list[Review], annotations: list[SemanticReview], budget: RoutingBudget | None = None
) -> dict:
    budget = budget or RoutingBudget()
    by_id = {review.review_id: review for review in reviews}
    semantic = {item.review_id: item for item in annotations}
    if (
        len(by_id) != len(reviews)
        or len(semantic) != len(annotations)
        or not semantic.keys() <= by_id.keys()
    ):
        raise ValueError("review and annotation IDs must be unique and within this dataset")
    cap = strict_review_cap(len(reviews))
    candidates = [
        item
        for item in annotations
        if item.processed
        and item.feedback_value == "actionable"
        and item.confidence.feedback_value is not None
        and item.confidence.feedback_value >= 0.6
    ]
    candidates.sort(key=lambda item: (-item.confidence.feedback_value, item.review_id))
    layers: dict[str, list[SemanticReview]] = defaultdict(list)
    for item in candidates:
        layers[_topic(item)].append(item)
    keys = [topic for topic in TOPICS if topic in layers]
    target = min(cap, len(candidates))
    quotas = dict.fromkeys(keys, 0)
    # When budget cannot cover every layer, choose the strongest layer, tie by fixed topic order.
    ranked_layers = sorted(
        keys, key=lambda key: (-layers[key][0].confidence.feedback_value, TOPICS.index(key))
    )
    for key in ranked_layers[:target]:
        quotas[key] = 1
    remaining = target - sum(quotas.values())
    weights = {key: len(layers[key]) - quotas[key] for key in keys}
    total_weight = sum(weights.values())
    if remaining and total_weight:
        for key in keys:
            quotas[key] += remaining * weights[key] // total_weight
        residual = target - sum(quotas.values())
        for key in sorted(
            keys, key=lambda key: (-(remaining * weights[key] % total_weight), TOPICS.index(key))
        ):
            if residual and quotas[key] < len(layers[key]):
                quotas[key] += 1
                residual -= 1
    order = [
        item
        for rank in range(max(quotas.values(), default=0))
        for key in ranked_layers
        for item in layers[key][rank : rank + 1]
        if rank < quotas[key]
    ]
    order += [item for item in candidates if item not in order]
    batches: list[list[str]] = []
    batch_costs: list[int] = []
    selected: list[str] = []
    skipped: list[str] = []
    capacity = max(0, budget.input_tokens - budget.reserved_input_tokens)
    run_cost = 0
    for item in order:
        if len(selected) >= target:
            break
        cost = _cost(by_id[item.review_id], item)
        if cost > capacity:
            skipped.append(item.review_id)
            continue
        new_batch = (
            not batches
            or len(batches[-1]) >= budget.batch_reviews
            or batch_costs[-1] + cost > capacity
        )
        overhead = budget.reserved_input_tokens + budget.output_tokens if new_batch else 0
        if run_cost + cost + overhead > budget.remaining_run_tokens:
            skipped.append(item.review_id)
            continue
        if new_batch:
            batches.append([])
            batch_costs.append(0)
        batches[-1].append(item.review_id)
        batch_costs[-1] += cost
        selected.append(item.review_id)
        run_cost += cost + overhead
    return {
        "valid_count": len(reviews),
        "strict_cap": cap,
        "candidate_ids": [i.review_id for i in candidates],
        "selected_ids": selected,
        "batches": batches,
        "batch_estimated_input_tokens": [
            cost + budget.reserved_input_tokens for cost in batch_costs
        ],
        "estimated_run_tokens": run_cost,
        "token_count_method": "estimated_utf8_bytes",
        "unselected_candidate_count": len(candidates) - len(selected),
        "token_skipped_ids": skipped,
        "method": "topic_stratified_largest_remainder",
        "threshold": 0.6,
    }


def selected_evidence(
    reviews: list[Review], allowed_ids: list[str], requested_ids: list[str]
) -> list[Review]:
    by_id = {review.review_id: review for review in reviews}
    if len(by_id) != len(reviews) or len(set(allowed_ids)) != len(allowed_ids):
        raise ValueError("duplicate evidence IDs")
    if not set(allowed_ids) <= by_id.keys() or not set(requested_ids) <= set(allowed_ids):
        raise ValueError("evidence outside fixed selection")
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("duplicate requested IDs")
    return [by_id[review_id] for review_id in requested_ids]
