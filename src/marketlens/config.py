"""Explicit LLM configuration; no key values in repr or error messages."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    structured_method: str = "json_mode"
    context_tokens: int = 16000
    input_tokens: int = 8000
    output_tokens: int = 2000
    run_tokens: int = 60000

    def __post_init__(self):
        try:
            url = urlsplit(self.base_url)
            valid = url.scheme in {"http", "https"} and url.hostname and url.username is None
            valid = (
                valid
                and not url.query
                and not url.fragment
                and not any(c.isspace() for c in self.base_url)
            )
            _ = url.port
        except ValueError:
            valid = False
        if not valid or not self.model.strip() or not self.api_key.strip():
            raise ConfigurationError("LLM address, model, or key is invalid")
        if self.structured_method not in {"json_mode", "json_schema"}:
            raise ConfigurationError("LLM_STRUCTURED_METHOD must be json_mode or json_schema")
        if (
            any(
                type(n) is not int or n <= 0
                for n in (
                    self.context_tokens,
                    self.input_tokens,
                    self.output_tokens,
                    self.run_tokens,
                )
            )
            or self.output_tokens >= self.context_tokens
        ):
            raise ConfigurationError("LLM token limits are invalid")

    @property
    def effective_input_tokens(self) -> int:
        return min(self.input_tokens, self.context_tokens - self.output_tokens)


def load_llm_config(
    env_path: Path | None = Path(".env"), environ: Mapping[str, str] | None = None
) -> LLMConfig:
    values: dict[str, str] = {}
    if env_path is not None and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                key, sep, value = line.partition("=")
                if not sep or not key.strip().startswith("LLM_"):
                    continue
                value = value.strip()
                if value.startswith(("'", '"')):
                    if len(value) < 2 or value[-1] != value[0]:
                        raise ConfigurationError("invalid quoted LLM configuration")
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].strip()
                values[key.strip()] = value
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError("cannot read LLM configuration") from exc
    values.update(os.environ if environ is None else environ)
    required = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
    missing = [key for key in required if not values.get(key, "").strip()]
    if missing:
        raise ConfigurationError("missing configuration: " + ", ".join(missing))
    try:
        return LLMConfig(
            base_url=values["LLM_BASE_URL"],
            model=values["LLM_MODEL"],
            api_key=values["LLM_API_KEY"],
            structured_method=values.get("LLM_STRUCTURED_METHOD", "json_mode"),
            context_tokens=int(values.get("LLM_CONTEXT_TOKENS", "16000")),
            input_tokens=int(values.get("LLM_INPUT_TOKENS", "8000")),
            output_tokens=int(values.get("LLM_OUTPUT_TOKENS", "2000")),
            run_tokens=int(values.get("LLM_RUN_TOKENS", "60000")),
        )
    except ValueError:
        raise ConfigurationError("invalid LLM configuration or token limits") from None
