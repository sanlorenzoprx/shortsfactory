from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RECOMMENDATION_TYPES = {
    "hooks", "scripts", "captions", "metadata", "longform", "critique",
}
LATENCY_CLASSES = {"fast", "balanced", "slow"}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
FORBIDDEN_CONFIG_KEYS = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)"
)
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

    def __post_init__(self) -> None:
        for name in ("model_id", "provider", "display_name", "endpoint_type", "safety_notes"):
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
        return cls(**{**value, "recommended_for": tuple(value.get("recommended_for", []))})

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["recommended_for"] = list(self.recommended_for)
        return value

    @property
    def profile_hash(self) -> str:
        return _canonical_hash(self.to_dict())


class LLMModelRegistry:
    def __init__(
        self,
        *,
        example_path: str | Path = DEFAULT_EXAMPLE_PATH,
        local_path: str | Path = DEFAULT_LOCAL_PATH,
    ):
        self.example_path = Path(example_path).expanduser().resolve()
        self.local_path = Path(local_path).expanduser().resolve()
        self._profiles = self._load()

    def _load(self) -> dict[str, LLMModelProfile]:
        profiles: dict[str, LLMModelProfile] = {}
        for path, required in ((self.example_path, True), (self.local_path, False)):
            if not path.is_file():
                if required:
                    raise LLMModelRegistryError(f"example model registry is missing: {path.name}")
                continue
            value = self._read_config(path)
            for raw in value["models"]:
                profile = LLMModelProfile.from_dict(raw)
                profiles[profile.model_id] = profile
        if not profiles:
            raise LLMModelRegistryError("model registry contains no profiles")
        return profiles

    @staticmethod
    def _read_config(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LLMModelRegistryError(f"model registry config is invalid: {path.name}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("models"), list):
            raise LLMModelRegistryError(f"model registry config must contain a models list: {path.name}")
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
        if require_json_schema and not profile.supports_json_schema:
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
            "secrets_recorded": False,
        }
