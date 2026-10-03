"""OpenAI-compatible JSON output, bounded retry, and usage accounting."""

import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from marketlens.config import LLMConfig


class LLMError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProviderError(LLMError):
    def __init__(self, retryable: bool):
        self.retryable = retryable
        super().__init__("provider_failed")


@dataclass(frozen=True)
class Response:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatBackend(Protocol):
    def complete(self, messages: list[dict[str, str]], schema: dict) -> Response: ...


class CompatibleChat:
    def __init__(self, config: LLMConfig, http_client: object | None = None):
        from langchain_openai import ChatOpenAI

        self.config = config
        self.client = ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            timeout=45,
            max_retries=0,
            max_tokens=config.output_tokens,
            http_client=http_client,
        )

    def complete(self, messages: list[dict[str, str]], schema: dict) -> Response:
        response_format = {"type": "json_object"}
        if self.config.structured_method == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "marketlens_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        try:
            raw = self.client.bind(response_format=response_format).invoke(messages)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            retryable = status in {408, 429} or isinstance(status, int) and status >= 500
            retryable = retryable or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
            raise ProviderError(retryable) from None
        usage = raw.usage_metadata or {}
        if not isinstance(raw.content, str):
            return Response("")
        return Response(raw.content, usage.get("input_tokens"), usage.get("output_tokens"))


class StructuredLLM:
    """One instance per run. Reservations bound unknown-cost failures and retries."""

    def __init__(self, config: LLMConfig, backend: ChatBackend | None = None):
        self.config = config
        self.backend = backend if backend is not None else CompatibleChat(config)
        self.calls: list[dict] = []
        self.charged_tokens = 0

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.config.run_tokens - self.charged_tokens)

    def _usage(self, response: Response | None, estimated_input: int) -> dict:
        valid = response is not None and all(
            type(value) is int and value >= 0
            for value in (response.input_tokens, response.output_tokens)
        )
        usage = {
            "input_tokens": response.input_tokens if valid else estimated_input,
            "output_tokens": response.output_tokens if valid else self.config.output_tokens,
            "method": "reported" if valid else "estimated_reserved",
        }
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        return usage

    def generate[T: BaseModel](
        self, output_type: type[T], system: str, payload: BaseModel | dict
    ) -> T:
        schema = output_type.model_json_schema()
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        messages = [
            {
                "role": "system",
                "content": system
                + "\n只返回一个JSON对象，必须符合Schema：\n"
                + json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
            },
            {
                "role": "user",
                "content": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        for attempt in range(2):
            estimated = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 64
            if self.config.structured_method == "json_schema":
                estimated += len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
            if estimated > self.config.effective_input_tokens:
                raise LLMError("input_budget_exceeded")
            reservation = estimated + self.config.output_tokens
            if reservation > self.remaining_tokens:
                raise LLMError("run_budget_exceeded")
            response = None
            failure = None
            retryable = False
            try:
                response = self.backend.complete(messages, schema)
            except ProviderError as exc:
                failure, retryable = exc.code, exc.retryable
            except Exception:
                failure = "provider_failed"
            usage = self._usage(response, estimated)
            self.charged_tokens += usage["total_tokens"]
            entry = {
                "attempt": attempt + 1,
                "schema": output_type.__name__,
                **usage,
                "status": failure or "received",
            }
            self.calls.append(entry)
            if failure:
                if retryable and attempt == 0:
                    continue
                raise LLMError(failure) from None
            try:
                result = output_type.model_validate_json(response.content)
            except (ValueError, ValidationError):
                entry["status"] = "invalid_output"
                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": "输出未通过校验。请只返回符合Schema的JSON，不添加字段。",
                        }
                    )
                    continue
                raise LLMError("invalid_output") from None
            entry["status"] = "complete"
            return result
        raise LLMError("invalid_output")

    def metrics(self) -> dict:
        return {
            "calls": list(self.calls),
            "charged_tokens": self.charged_tokens,
            "remaining_tokens": self.remaining_tokens,
            "usage_is_estimated": any(call["method"] != "reported" for call in self.calls),
        }
