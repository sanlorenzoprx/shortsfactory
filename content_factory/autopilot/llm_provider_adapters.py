from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .llm_model_registry import LLMModelProfile


DEFAULT_CREATIVE_FIXTURE = Path("fixtures/lit_verdicts/sample.json")
SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+\S+|(?:access|refresh)[_-]?token\s*[:=]\s*\S+|client[_-]?secret\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+)"
)
AUTH_URL_PATTERN = re.compile(r"(?i)https?://[^\s\"<>]*(?:oauth|authorize|token_uri)[^\s\"<>]*")


class LLMAdapterError(RuntimeError):
    pass


class LLMProviderAdapter(ABC):
    adapter_type = "abstract"

    def __init__(self) -> None:
        self.network_called = False
        self.estimated_input_tokens = 0
        self.estimated_output_tokens = 0
        self.estimated_cost = 0.0
        self.raw_response_stored = False

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        model_profile: LLMModelProfile,
    ) -> Any:
        raise NotImplementedError

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model_profile: LLMModelProfile,
    ) -> float | None:
        input_rate = model_profile.cost_per_1m_input_tokens
        output_rate = model_profile.cost_per_1m_output_tokens
        if input_rate is None or output_rate is None:
            return None
        return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)

    def redact_response(self, raw_response: Any) -> dict[str, Any]:
        if isinstance(raw_response, dict):
            safe_keys = [
                "<redacted-key>" if re.search(r"(?i)(token|secret|authorization|api.?key)", str(key)) else str(key)
                for key in raw_response
            ]
            return {
                "response_type": "object",
                "top_level_keys": sorted(safe_keys)[:20],
                "secrets_recorded": False,
                "raw_response_stored": False,
            }
        return {
            "response_type": type(raw_response).__name__,
            "secrets_recorded": False,
            "raw_response_stored": False,
        }

    @abstractmethod
    def healthcheck(self) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return max(1, (len(text) + 3) // 4)

    def _record_usage(self, prompt: str, output: Any, profile: LLMModelProfile) -> None:
        input_tokens = self._estimate_tokens(prompt)
        output_tokens = self._estimate_tokens(output)
        if input_tokens > profile.max_input_tokens:
            raise LLMAdapterError("prompt exceeds the selected model input-token limit")
        if output_tokens > profile.max_output_tokens:
            raise LLMAdapterError("output exceeds the selected model output-token limit")
        self.estimated_input_tokens += input_tokens
        self.estimated_output_tokens += output_tokens
        cost = self.estimate_cost(input_tokens, output_tokens, profile)
        if cost is not None:
            self.estimated_cost = round(self.estimated_cost + cost, 8)


class LocalFixtureLLMAdapter(LLMProviderAdapter):
    adapter_type = "local_fixture"

    def __init__(self, fixture_path: str | Path = DEFAULT_CREATIVE_FIXTURE) -> None:
        super().__init__()
        self.fixture_path = Path(fixture_path).expanduser().resolve()

    def _creative_output(self) -> dict[str, Any]:
        if not self.fixture_path.is_file():
            raise LLMAdapterError(f"LLM fixture is missing: {self.fixture_path.name}")
        try:
            value = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LLMAdapterError("LLM fixture is invalid") from exc
        output = value.get("creative_output") if isinstance(value, dict) else None
        if not isinstance(output, dict):
            raise LLMAdapterError("LLM fixture has no creative_output")
        return output

    @staticmethod
    def _prompt_value(prompt: str) -> tuple[str, dict[str, Any]]:
        try:
            value = json.loads(prompt)
        except json.JSONDecodeError as exc:
            raise LLMAdapterError("adapter prompt is not structured JSON") from exc
        if not isinstance(value, dict) or not isinstance(value.get("task"), str) or not isinstance(value.get("input"), dict):
            raise LLMAdapterError("adapter prompt is missing task or input")
        return value["task"], value["input"]

    def _fixture_result(self, task: str, payload: dict[str, Any]) -> Any:
        output = self._creative_output()
        if task == "registry_healthcheck":
            return {"ok": True}
        if task == "generate_angle_pack":
            return {"angles": deepcopy(output.get("angles"))}
        angle = payload.get("angle", {})
        angle_id = angle.get("angle_id") if isinstance(angle, dict) else None
        short = output.get("shorts", {}).get(angle_id, {})
        if task == "generate_short_script":
            return {key: deepcopy(short.get(key)) for key in ("hook", "script", "cta")}
        if task == "generate_title_variants":
            return {"title_variants": deepcopy(short.get("title_variants"))}
        if task == "generate_thumbnail_text":
            return {"thumbnail_text": short.get("thumbnail_text")}
        if task == "generate_caption":
            return {"caption": short.get("caption")}
        if task == "generate_youtube_metadata_draft":
            return deepcopy(short.get("youtube_metadata_draft"))
        if task == "generate_longform_assembly_plan":
            plan = deepcopy(output.get("longform"))
            if not isinstance(plan, dict):
                return plan
            jobs = payload.get("short_jobs", [])
            for index, chapter in enumerate(plan.get("ordered_chapters", [])):
                if index < len(jobs) and isinstance(jobs[index], dict):
                    chapter["job_id"] = jobs[index].get("job_id")
            return plan
        raise LLMAdapterError(f"unsupported creative generation task: {task}")

    def generate_json(
        self, prompt: str, schema: dict[str, Any], model_profile: LLMModelProfile,
    ) -> Any:
        task, payload = self._prompt_value(prompt)
        result = self._fixture_result(task, payload)
        self._record_usage(prompt, result, model_profile)
        return result

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.fixture_path.is_file() else "blocked",
            "adapter_type": self.adapter_type,
            "fixture_path": str(self.fixture_path),
            "network_called": False,
            "secrets_recorded": False,
        }


class FakeLLMAdapter(LocalFixtureLLMAdapter):
    adapter_type = "fake"

    def __init__(
        self,
        fixture_path: str | Path = DEFAULT_CREATIVE_FIXTURE,
        *,
        response_mode: str = "valid",
    ) -> None:
        super().__init__(fixture_path)
        self.response_mode = response_mode

    def generate_json(
        self, prompt: str, schema: dict[str, Any], model_profile: LLMModelProfile,
    ) -> Any:
        if self.response_mode == "malformed_json":
            raise LLMAdapterError("adapter returned malformed JSON")
        if self.response_mode == "schema_invalid":
            result = {"angles": [{"angle_id": "invalid"}]}
            self._record_usage(prompt, result, model_profile)
            return result
        return super().generate_json(prompt, schema, model_profile)

    def healthcheck(self) -> dict[str, Any]:
        value = super().healthcheck()
        value["adapter_type"] = self.adapter_type
        value["response_mode"] = self.response_mode
        return value


class GenericHTTPAdapter(LLMProviderAdapter):
    adapter_type = "generic_http"

    def __init__(
        self,
        *,
        endpoint_url: str | None,
        api_key: str | None,
        timeout_seconds: float = 45.0,
        allow_network: bool = False,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__()
        self.endpoint_url = (endpoint_url or "").strip()
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds
        self.allow_network = allow_network
        self._transport = transport

    @classmethod
    def from_environment(
        cls,
        profile: LLMModelProfile,
        *,
        allow_network: bool,
        require_config: bool,
        transport: Callable[..., Any] | None = None,
    ) -> "GenericHTTPAdapter":
        prefix = "LLM_" + re.sub(r"[^A-Za-z0-9]", "_", profile.provider).upper()
        endpoint = os.getenv(f"{prefix}_API_URL") or os.getenv("CREATIVE_LLM_API_URL")
        api_key = os.getenv(f"{prefix}_API_KEY") or os.getenv("CREATIVE_LLM_API_KEY")
        timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS") or os.getenv("CREATIVE_LLM_TIMEOUT_SECONDS") or "45"
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise LLMAdapterError(f"{prefix}_TIMEOUT_SECONDS must be numeric") from exc
        adapter = cls(
            endpoint_url=endpoint,
            api_key=api_key,
            timeout_seconds=timeout,
            allow_network=allow_network,
            transport=transport,
        )
        if require_config:
            adapter._validate_config()
        return adapter

    def _validate_config(self) -> None:
        if not self.endpoint_url or not self.api_key:
            raise LLMAdapterError("generic HTTP model requires provider API URL and API key environment configuration")
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise LLMAdapterError("provider API URL must be a safe HTTP(S) endpoint")
        if "youtube" in parsed.netloc.casefold() or "youtube" in parsed.path.casefold():
            raise LLMAdapterError("provider API URL must not target a YouTube API")
        if self.timeout_seconds <= 0:
            raise LLMAdapterError("provider timeout must be positive")

    def generate_json(
        self, prompt: str, schema: dict[str, Any], model_profile: LLMModelProfile,
    ) -> Any:
        self._validate_config()
        if not self.allow_network:
            raise LLMAdapterError("live LLM network call requires explicit confirmation")
        if not model_profile.supports_json_schema:
            raise LLMAdapterError("selected model does not support required JSON schema output")
        body = {
            "model": model_profile.model_id,
            "messages": [
                {"role": "system", "content": "Return only schema-valid JSON. Never publish or call platform APIs."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "creative_generation", "strict": True, "schema": schema},
            },
            "max_tokens": model_profile.max_output_tokens,
        }
        self.network_called = True
        try:
            if self._transport is None:
                import requests

                response = requests.post(
                    self.endpoint_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._transport(
                    url=self.endpoint_url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=self.timeout_seconds,
                )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            raw = response.json() if hasattr(response, "json") else response
            value = self._structured_value(raw)
            self._record_usage(prompt, value, model_profile)
            return value
        except LLMAdapterError:
            raise
        except Exception as exc:
            raise LLMAdapterError(f"generic HTTP LLM request failed: {type(exc).__name__}") from exc

    @staticmethod
    def _structured_value(raw: Any) -> Any:
        if not isinstance(raw, dict):
            raise LLMAdapterError("LLM response is not a JSON object")
        value: Any = raw.get("result", raw.get("output"))
        if value is None:
            choices = raw.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message", {})
                value = message.get("content") if isinstance(message, dict) else None
        if value is None:
            value = raw.get("output_text")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise LLMAdapterError("LLM response contains malformed JSON") from exc
        if not isinstance(value, (dict, list)):
            raise LLMAdapterError("LLM response has no structured JSON output")
        encoded = json.dumps(value, ensure_ascii=False)
        if SECRET_PATTERN.search(encoded) or AUTH_URL_PATTERN.search(encoded):
            raise LLMAdapterError("LLM response contains secrets or authentication URLs")
        return value

    def healthcheck(self) -> dict[str, Any]:
        try:
            self._validate_config()
            status = "ready"
        except LLMAdapterError:
            status = "blocked_missing_config"
        return {
            "status": status,
            "adapter_type": self.adapter_type,
            "network_confirmation": self.allow_network,
            "network_called": False,
            "secrets_recorded": False,
        }


def build_llm_adapter(
    profile: LLMModelProfile,
    *,
    allow_network: bool,
    require_config: bool = True,
    fixture_path: str | Path = DEFAULT_CREATIVE_FIXTURE,
    transport: Callable[..., Any] | None = None,
) -> LLMProviderAdapter:
    if profile.endpoint_type == "fake_json":
        return FakeLLMAdapter(fixture_path)
    if profile.endpoint_type == "local_fixture":
        return LocalFixtureLLMAdapter(fixture_path)
    if profile.endpoint_type == "generic_http":
        return GenericHTTPAdapter.from_environment(
            profile,
            allow_network=allow_network,
            require_config=require_config,
            transport=transport,
        )
    raise LLMAdapterError(f"unsupported model endpoint_type: {profile.endpoint_type}")
