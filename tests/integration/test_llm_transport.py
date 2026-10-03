"""Real LangChain/OpenAI request serialization through an offline HTTP transport."""

import json

import pytest

from marketlens.adapters.llm import CompatibleChat, StructuredLLM
from marketlens.config import LLMConfig
from marketlens.contracts import PlannerOutput

httpx = pytest.importorskip("httpx")
pytest.importorskip("langchain_openai")


@pytest.mark.parametrize("method", ["json_mode", "json_schema"])
def test_compatible_transport_schema_usage_and_no_sdk_retries(method):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                500, json={"error": {"message": "private detail", "type": "server_error"}}
            )
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "sources": ["local"],
                                    "keywords": ["示例"],
                                    "dimensions": ["pain_point"],
                                }
                            ),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    config = LLMConfig(
        "https://provider.example/v1",
        "fixture-model",
        "sanitized-test-key",
        structured_method=method,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        llm = StructuredLLM(config, CompatibleChat(config, http_client=client))
        assert llm.generate(PlannerOutput, "plan", {}).sources == ["local"]
    assert len(requests) == 2  # one app retry, no nested SDK retries
    assert requests[0]["model"] == "fixture-model"
    assert requests[0]["response_format"]["type"] == (
        "json_object" if method == "json_mode" else "json_schema"
    )
    assert requests[0].get("max_completion_tokens", requests[0].get("max_tokens")) == 2000
    assert llm.calls[-1]["input_tokens"] == 100
    assert llm.calls[-1]["output_tokens"] == 20
    assert "private" not in repr(llm.metrics())
