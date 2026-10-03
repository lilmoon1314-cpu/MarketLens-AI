"""GLiNER2 span inference; no LLM fallback and no invented confidence scores."""

import math
from contextlib import redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Protocol, get_args

from marketlens.contracts import Review, SemanticReview
from marketlens.contracts.models import Topic

MODEL_ID = "fastino/gliner2-multi-v1"
MODEL_REVISION = "ce747d79a8e362d3dee0b0b26d1201f7f1a8615a"
TOPICS = get_args(Topic)


class Backend(Protocol):
    def prepare(self, text: str) -> tuple[str, bool]: ...
    def extract(self, texts: list[str], batch_size: int) -> list[dict]: ...


@dataclass(frozen=True)
class GLiNERConfig:
    cache_dir: Path = Path(".local/huggingface/hub")
    splitter: str = "char"
    label_language: str = "zh"
    batch_size: int = 8

    def __post_init__(self):
        if self.splitter not in {"char", "whitespace"} or self.label_language not in {"zh", "en"}:
            raise ValueError("invalid splitter or label language")
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 32:
            raise ValueError("batch_size must be between 1 and 32")


def build_schema(model, language: str):
    values = {
        "actionable": "具体问题、明确收益、使用情境或改进需求"
        if language == "zh"
        else "Specific product issue, benefit, usage context, or improvement request",
        "non_actionable": "笼统情绪或评价，没有具体产品信息"
        if language == "zh"
        else "Generic emotion or rating without specific product information",
        "spam": "广告、引流或与产品无关的推广"
        if language == "zh"
        else "Advertising, promotion, or unrelated content",
    }
    return (
        model.create_schema()
        .classification("sentiment", ["positive", "negative", "neutral", "mixed"])
        .classification("topics", list(TOPICS), multi_label=True, cls_threshold=0.4)
        .classification("feedback_value", values)
    )


class LocalBackend:
    def __init__(self, config: GLiNERConfig):
        from gliner2 import GLiNER2
        from huggingface_hub import snapshot_download

        snapshot = snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=config.cache_dir,
            allow_patterns=["*.json", "*.model", "model.safetensors", "encoder_config/config.json"],
        )
        with redirect_stdout(StringIO()):
            self.model = GLiNER2.from_pretrained(snapshot, map_location="cpu")
        self.model.set_word_splitter(config.splitter)
        self.model.eval()
        self.schema = build_schema(self.model, config.label_language)
        self.limit = int(self.model.encoder.config.max_position_embeddings)
        self.word_limit = getattr(self.model, "max_len", None) or self.limit

    def _fits(self, text: str) -> bool:
        batch = self.model.processor.collate_fn_inference(
            [(text, self.schema)], error_policy="raise"
        )
        return batch.input_ids.shape[1] <= self.limit

    def prepare(self, text: str) -> tuple[str, bool]:
        tokens = list(self.model.processor.word_splitter(text, lower=True))
        view = text[: tokens[self.word_limit - 1][2]] if len(tokens) > self.word_limit else text
        if not self._fits(view):
            lo, hi = 0, len(view)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if self._fits(view[:mid]):
                    lo = mid
                else:
                    hi = mid - 1
            view = view[:lo]
        if not view.strip() or not self._fits(view):
            raise ValueError("schema leaves no text capacity")
        return view, view != text

    def extract(self, texts: list[str], batch_size: int) -> list[dict]:
        return self.model.batch_extract(
            texts,
            self.schema,
            batch_size=batch_size,
            include_confidence=True,
            num_workers=0,
            max_len=self.word_limit,
        )


@lru_cache(maxsize=2)
def local_backend(config: GLiNERConfig) -> LocalBackend:
    """Reuse CPU model within the process, including Streamlit reruns."""
    return LocalBackend(config)


def _score(value: object) -> float | None:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return float(value)


def _label(value: object, allowed: tuple[str, ...], threshold: float) -> tuple[str, float | None]:
    if not isinstance(value, dict):
        return "unknown", None
    score = _score(value.get("confidence"))
    label = value.get("label")
    return (
        label if label in allowed and score is not None and score >= threshold else "unknown",
        score,
    )


def unknown(review_id: str, truncated: bool = False) -> SemanticReview:
    return SemanticReview(
        review_id=review_id,
        sentiment="unknown",
        topics=[],
        feedback_value="unknown",
        confidence={"sentiment": None, "topics": {}, "feedback_value": None},
        processed=False,
        truncated=truncated,
    )


def convert(review_id: str, output: dict, truncated: bool) -> SemanticReview:
    if (
        not isinstance(output, dict)
        or not {"sentiment", "topics", "feedback_value"} <= output.keys()
    ):
        return unknown(review_id, truncated)
    sentiment, sentiment_score = _label(
        output["sentiment"], ("positive", "negative", "neutral", "mixed"), 0.5
    )
    value, value_score = _label(
        output["feedback_value"], ("actionable", "non_actionable", "spam"), 0.5
    )
    scores: dict[str, float] = {}
    if isinstance(output["topics"], list):
        for item in output["topics"]:
            topic, score = _label(item, TOPICS, 0.4)
            if topic != "unknown":
                scores[topic] = max(score, scores.get(topic, 0.0))
    topics = [topic for topic in TOPICS if topic in scores]
    return SemanticReview(
        review_id=review_id,
        sentiment=sentiment,
        topics=topics or ["other"],
        feedback_value=value,
        confidence={"sentiment": sentiment_score, "topics": scores, "feedback_value": value_score},
        processed=True,
        truncated=truncated,
    )


class SemanticAnalyzer:
    def __init__(self, config: GLiNERConfig | None = None, backend: Backend | None = None):
        self.config = config or GLiNERConfig()
        self.backend = backend

    def analyze(self, reviews: list[Review]) -> list[SemanticReview]:
        if not reviews:
            return []
        backend = self.backend if self.backend is not None else local_backend(self.config)
        results = [unknown(review.review_id) for review in reviews]
        prepared: list[tuple[int, str, bool]] = []
        for index, review in enumerate(reviews):
            try:
                view, truncated = backend.prepare(review.text)
                prepared.append((index, view, truncated))
                results[index] = unknown(review.review_id, truncated)
            except Exception:
                continue
        for start in range(0, len(prepared), self.config.batch_size):
            batch = prepared[start : start + self.config.batch_size]
            outputs = None
            for size in (self.config.batch_size, max(1, self.config.batch_size // 2)):
                try:
                    outputs = backend.extract([item[1] for item in batch], size)
                    if not isinstance(outputs, list) or len(outputs) != len(batch):
                        raise ValueError("result count mismatch")
                    break
                except Exception:
                    outputs = None
            if outputs is not None:
                for (index, _, truncated), output in zip(batch, outputs, strict=True):
                    results[index] = convert(reviews[index].review_id, output, truncated)
        return results
