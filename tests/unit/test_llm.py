"""Offline provider fixtures for validation, retry, and cumulative cost accounting."""

import json

import pytest

from marketlens.adapters.llm import LLMError, ProviderError, Response, StructuredLLM
from marketlens.config import ConfigurationError, LLMConfig, load_llm_config
from marketlens.contracts import PlannerOutput


def config(**kwargs):
    return LLMConfig(
        base_url="https://provider.example/v1",
        model="fixture-model",
        api_key="secret-test-key",
        **kwargs,
    )


def valid():
    return json.dumps({"sources": ["local"], "keywords": ["示例"], "dimensions": ["pain_point"]})


class Fake:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.messages = []

    def complete(self, messages, schema):
        self.messages.append(json.loads(json.dumps(messages)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_valid_chinese_output_and_usage():
    backend = Fake(Response(valid(), 100, 20))
    llm = StructuredLLM(config(), backend)
    result = llm.generate(PlannerOutput, "规划任务", {"product": "示例"})
    assert result.sources == ["local"]
    assert llm.charged_tokens == 120
    assert llm.remaining_tokens == 59880
    assert llm.calls[0]["method"] == "reported"
    assert "secret-test-key" not in repr(llm.metrics())
    assert "Schema" in backend.messages[0][0]["content"]


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        "{}",
        valid()[:-1] + ',"extra":true}',
        '{"sources":["bad"],"keywords":["x"],"dimensions":["pain_point"]}',
    ],
)
def test_invalid_output_retries_once_and_counts_both(bad):
    backend = Fake(Response(bad, 100, 10), Response(valid(), 120, 20))
    llm = StructuredLLM(config(), backend)
    assert llm.generate(PlannerOutput, "plan", {}).keywords == ["示例"]
    assert llm.charged_tokens == 250
    assert len(backend.messages) == 2
    assert [call["status"] for call in llm.calls] == ["invalid_output", "complete"]
    assert len(backend.messages[1]) == 3


def test_two_invalid_outputs_are_terminal():
    backend = Fake(Response("bad"), Response("bad"))
    llm = StructuredLLM(config(), backend)
    with pytest.raises(LLMError, match="invalid_output"):
        llm.generate(PlannerOutput, "plan", {})
    assert len(llm.calls) == 2
    assert llm.metrics()["usage_is_estimated"]


def test_transient_failure_retry_uses_full_reservation():
    backend = Fake(ProviderError(True), Response(valid(), 100, 20))
    llm = StructuredLLM(config(), backend)
    llm.generate(PlannerOutput, "plan", {})
    assert len(llm.calls) == 2
    assert llm.calls[0]["method"] == "estimated_reserved"
    assert llm.calls[0]["output_tokens"] == 2000
    assert llm.charged_tokens > 2120


@pytest.mark.parametrize("error", [ProviderError(False), RuntimeError("private credential")])
def test_permanent_failure_is_safe_and_not_retried(error):
    llm = StructuredLLM(config(), Fake(error))
    with pytest.raises(LLMError) as captured:
        llm.generate(PlannerOutput, "plan", {})
    assert str(captured.value) == "provider_failed"
    assert "private" not in repr(llm.metrics())
    assert len(llm.calls) == 1


def test_input_and_run_budgets_prevent_calls():
    backend = Fake()
    for options, code in [
        ({"input_tokens": 100}, "input_budget_exceeded"),
        ({"run_tokens": 100}, "run_budget_exceeded"),
        ({"context_tokens": 2100}, "input_budget_exceeded"),
    ]:
        llm = StructuredLLM(config(**options), backend)
        with pytest.raises(LLMError, match=code):
            llm.generate(PlannerOutput, "plan", {})
        assert llm.calls == []
    assert backend.messages == []


def test_retry_cannot_exceed_remaining_budget():
    llm = StructuredLLM(config(run_tokens=3000), Fake(Response("bad")))
    with pytest.raises(LLMError, match="run_budget_exceeded"):
        llm.generate(PlannerOutput, "plan", {})
    assert len(llm.calls) == 1
    assert llm.remaining_tokens < 2000


@pytest.mark.parametrize("usage", [(None, None), (True, 10), (-1, 10), (100, "20")])
def test_unusable_usage_is_estimated(usage):
    llm = StructuredLLM(config(), Fake(Response(valid(), *usage)))
    llm.generate(PlannerOutput, "plan", {})
    assert llm.calls[0]["method"] == "estimated_reserved"
    assert llm.calls[0]["output_tokens"] == 2000


def test_configuration_file_precedence_quotes_and_secrecy(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        '# comment\nexport LLM_BASE_URL="https://provider.example/v1"\n'
        "LLM_API_KEY=secret-test-key\nLLM_MODEL=old # comment\n",
        encoding="utf-8-sig",
    )
    loaded = load_llm_config(path, {"LLM_MODEL": "new"})
    assert loaded.model == "new"
    assert loaded.api_key == "secret-test-key"
    assert "secret-test-key" not in repr(loaded)
    with pytest.raises(ConfigurationError, match="missing"):
        load_llm_config(None, {})


@pytest.mark.parametrize(
    "options",
    [
        {"base_url": "file:///path"},
        {"base_url": "https://key@example.com"},
        {"base_url": "https://example.com?key=secret"},
        {"structured_method": "function_calling"},
        {"run_tokens": 0},
        {"input_tokens": True},
        {"context_tokens": 1000},
        {"model": " "},
        {"api_key": ""},
    ],
)
def test_bad_configuration_is_safe(options):
    values = {
        "base_url": "https://provider.example/v1",
        "model": "fixture-model",
        "api_key": "secret-test-key",
    }
    values.update(options)
    with pytest.raises(ConfigurationError) as captured:
        LLMConfig(**values)
    assert "secret-test-key" not in str(captured.value)
