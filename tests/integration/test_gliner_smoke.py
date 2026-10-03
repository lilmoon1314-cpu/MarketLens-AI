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
