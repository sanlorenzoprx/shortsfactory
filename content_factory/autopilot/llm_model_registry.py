from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RECOMMENDATION_TYPES = {
    "hooks", "scripts", "captions", "metadata", "longform", "critique",
}
LATENCY_CLASSES = {"fast", "balanced", "slow"}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
FORBIDDEN_CONFIG_KEYS = re.compile(
    r"(?i)^(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)$"
)
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFAULT_EXAMPLE_PATH = Path("config/examples/llm_models.example.json")
DEFAULT_LOCAL_PATH = Path(".local/llm/models.json")


class LLMModelRegistryError(ValueError):
    pass


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LLMModelProfile:
    model_id: str
    provider: str
    provider_model: str
    display_name: str
    endpoint_type: str
    supports_json_schema: bool
    supports_tool_calling: bool
    max_input_tokens: int
    max_output_tokens: int
    cost_per_1m_input_tokens: float | None
    cost_per_1m_output_tokens: float | None
    latency_class: str
    recommended_for: tuple[str, ...]
    safety_notes: str
    enabled: bool
    api_key_env: str | None = None
    base_url_env: str | None = None
    allow_localhost: bool = False
    http_referer_env: str | None = None
    app_title_env: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "model_id", "provider", "provider_model", "display_name", "endpoint_type", "safety_notes",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LLMModelRegistryError(f"{name} is required")
        if not SAFE_ID.fullmatch(self.model_id):
            raise LLMModelRegistryError("model_id contains unsafe characters")
        if not SAFE_ID.fullmatch(self.provider):
            raise LLMModelRegistryError("provider contains unsafe characters")
        if not isinstance(self.supports_json_schema, bool) or not isinstance(self.supports_tool_calling, bool):
            raise LLMModelRegistryError("model capabilities must be boolean")
        if not isinstance(self.enabled, bool):
            raise LLMModelRegistryError("enabled must be boolean")
        for name in ("api_key_env", "base_url_env", "http_referer_env", "app_title_env"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not ENV_NAME.fullmatch(value)):
                raise LLMModelRegistryError(f"{name} must be null or a safe environment variable name")
        if not isinstance(self.allow_localhost, bool):
            raise LLMModelRegistryError("allow_localhost must be boolean")
        if not isinstance(self.max_input_tokens, int) or self.max_input_tokens < 1:
            raise LLMModelRegistryError("max_input_tokens must be a positive integer")
        if not isinstance(self.max_output_tokens, int) or self.max_output_tokens < 1:
            raise LLMModelRegistryError("max_output_tokens must be a positive integer")
        for name in ("cost_per_1m_input_tokens", "cost_per_1m_output_tokens"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0):
                raise LLMModelRegistryError(f"{name} must be null or non-negative")
        if self.latency_class not in LATENCY_CLASSES:
            raise LLMModelRegistryError("latency_class must be fast, balanced, or slow")
        if not self.recommended_for or not set(self.recommended_for).issubset(RECOMMENDATION_TYPES):
            raise LLMModelRegistryError("recommended_for contains unsupported values")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LLMModelProfile":
        if not isinstance(value, dict):
            raise LLMModelRegistryError("model profile must be a JSON object")
        if not str(value.get("provider_model", "")).strip():
            raise LLMModelRegistryError("provider_model is required")
        if value.get("endpoint_type") in {"generic_http", "chat_json"}:
            missing = [name for name in ("api_key_env", "base_url_env") if name not in value]
            if missing:
                raise LLMModelRegistryError("HTTP model profile is missing: " + ", ".join(missing))
        return cls(**{**value, "recommended_for": tuple(value.get("recommended_for", []))})

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["recommended_for"] = list(self.recommended_for)
        return value

    @property
    def profile_hash(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True)
class LLMFallbackGroup:
    fallback_group_id: str
    model_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not SAFE_ID.fullmatch(self.fallback_group_id):
            raise LLMModelRegistryError("fallback_group_id contains unsafe characters")
        if not self.model_ids or len(set(self.model_ids)) != len(self.model_ids):
            raise LLMModelRegistryError("fallback group requires unique ordered model IDs")
        if any(not isinstance(model_id, str) or not SAFE_ID.fullmatch(model_id) for model_id in self.model_ids):
            raise LLMModelRegistryError("fallback group contains an unsafe model ID")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LLMFallbackGroup":
        if not isinstance(value, dict) or not isinstance(value.get("models"), list):
            raise LLMModelRegistryError("fallback group must contain a models list")
        return cls(
            fallback_group_id=str(value.get("fallback_group_id", "")),
            model_ids=tuple(value["models"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"fallback_group_id": self.fallback_group_id, "models": list(self.model_ids)}


class LLMModelRegistry:
    def __init__(
        self,
        *,
        example_path: str | Path = DEFAULT_EXAMPLE_PATH,
        local_path: str | Path = DEFAULT_LOCAL_PATH,
    ):
        self.example_path = Path(example_path).expanduser().resolve()
        self.local_path = Path(local_path).expanduser().resolve()
        self._profiles, self._fallback_groups = self._load()

    def _load(self) -> tuple[dict[str, LLMModelProfile], dict[str, LLMFallbackGroup]]:
        profiles: dict[str, LLMModelProfile] = {}
        fallback_groups: dict[str, LLMFallbackGroup] = {}
        for path, required in ((self.example_path, True), (self.local_path, False)):
            if not path.is_file():
                if required:
                    raise LLMModelRegistryError(f"example model registry is missing: {path.name}")
                continue
            value = self._read_config(path)
            for raw in value["models"]:
                profile = LLMModelProfile.from_dict(raw)
                profiles[profile.model_id] = profile
            for raw in value.get("fallback_groups", []):
                group = LLMFallbackGroup.from_dict(raw)
                fallback_groups[group.fallback_group_id] = group
        if not profiles:
            raise LLMModelRegistryError("model registry contains no profiles")
        for group in fallback_groups.values():
            missing = [model_id for model_id in group.model_ids if model_id not in profiles]
            if missing:
                raise LLMModelRegistryError(
                    f"fallback group {group.fallback_group_id} references missing models: " + ", ".join(missing)
                )
        return profiles, fallback_groups

    @staticmethod
    def _read_config(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LLMModelRegistryError(f"model registry config is invalid: {path.name}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("models"), list):
            raise LLMModelRegistryError(f"model registry config must contain a models list: {path.name}")
        if "fallback_groups" in value and not isinstance(value["fallback_groups"], list):
            raise LLMModelRegistryError(f"model registry fallback_groups must be a list: {path.name}")
        if LLMModelRegistry._contains_forbidden_key(value):
            raise LLMModelRegistryError(f"model registry profiles must not contain credentials: {path.name}")
        return value

    @staticmethod
    def _contains_forbidden_key(value: Any) -> bool:
        if isinstance(value, dict):
            return any(FORBIDDEN_CONFIG_KEYS.search(str(key)) or LLMModelRegistry._contains_forbidden_key(child) for key, child in value.items())
        if isinstance(value, list):
            return any(LLMModelRegistry._contains_forbidden_key(child) for child in value)
        return False

    def list_profiles(self, *, include_disabled: bool = True) -> tuple[LLMModelProfile, ...]:
        return tuple(
            profile for profile in sorted(self._profiles.values(), key=lambda row: row.model_id)
            if include_disabled or profile.enabled
        )

    def get(self, model_id: str) -> LLMModelProfile | None:
        return self._profiles.get(model_id)

    def list_fallback_groups(self) -> tuple[LLMFallbackGroup, ...]:
        return tuple(sorted(self._fallback_groups.values(), key=lambda row: row.fallback_group_id))

    def get_fallback_group(self, fallback_group_id: str) -> LLMFallbackGroup | None:
        return self._fallback_groups.get(fallback_group_id)

    def require_fallback_group(self, fallback_group_id: str | None) -> tuple[LLMFallbackGroup, tuple[LLMModelProfile, ...]]:
        if not fallback_group_id:
            raise LLMModelRegistryError("online_llm requires --fallback-group <fallback_group_id>")
        group = self.get_fallback_group(fallback_group_id)
        if group is None:
            raise LLMModelRegistryError(f"fallback group not found in registry: {fallback_group_id}")
        profiles = tuple(self.require(model_id, require_json_schema=True) for model_id in group.model_ids)
        return group, profiles

    def require(
        self,
        model_id: str | None,
        *,
        require_enabled: bool = True,
        require_json_schema: bool = False,
    ) -> LLMModelProfile:
        if not model_id:
            raise LLMModelRegistryError("online_llm requires --model <model_id>")
        profile = self.get(model_id)
        if profile is None:
            raise LLMModelRegistryError(f"model not found in registry: {model_id}")
        if require_enabled and not profile.enabled:
            raise LLMModelRegistryError(f"model is disabled: {model_id}")
        local_client_validation = profile.allow_localhost and profile.endpoint_type == "chat_json"
        if require_json_schema and not profile.supports_json_schema and not local_client_validation:
            raise LLMModelRegistryError(f"model lacks required JSON schema capability: {model_id}")
        return profile

    def validate(self) -> dict[str, Any]:
        profiles = self.list_profiles()
        return {
            "status": "valid",
            "example_path": str(self.example_path),
            "local_path": str(self.local_path),
            "local_config_present": self.local_path.is_file(),
            "profile_count": len(profiles),
            "enabled_count": sum(profile.enabled for profile in profiles),
            "disabled_count": sum(not profile.enabled for profile in profiles),
            "fallback_group_count": len(self._fallback_groups),
            "secrets_recorded": False,
        }

    @classmethod
    def init_local_config(
        cls,
        *,
        local_path: str | Path = DEFAULT_LOCAL_PATH,
        example_path: str | Path = DEFAULT_EXAMPLE_PATH,
        force: bool = False,
        ignore_checker=None,
    ) -> Path:
        path = Path(local_path).expanduser().resolve()
        checker = ignore_checker or cls._git_ignored
        if not checker(path):
            raise LLMModelRegistryError("local LLM config path is not protected by Git ignore rules")
        if path.exists() and not force:
            raise LLMModelRegistryError("local LLM config already exists; pass --force to replace it")
        examples = cls._read_config(Path(example_path).expanduser().resolve())
        source = next(
            (profile for profile in examples["models"] if profile.get("endpoint_type") == "generic_http"),
            None,
        )
        if not isinstance(source, dict):
            raise LLMModelRegistryError("safe example config has no generic HTTP profile")
        profile = {
            **source,
            "model_id": "real-creative-model",
            "provider": "generic_http",
            "provider_model": "replace-with-provider-model",
            "display_name": "Real Creative Model",
            "endpoint_type": "chat_json",
            "max_input_tokens": 120000,
            "max_output_tokens": 8000,
            "safety_notes": "Online provider must return structured JSON only.",
            "enabled": True,
            "api_key_env": "LLM_API_KEY",
            "base_url_env": "LLM_BASE_URL",
            "allow_localhost": False,
            "http_referer_env": None,
            "app_title_env": None,
        }
        value = {"schema_version": "llm_model_registry.v1", "models": [profile]}
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".llm-models.", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        cls._read_config(path)
        return path

    @staticmethod
    def _git_ignored(path: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", str(path)],
                cwd=Path.cwd(),
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0
