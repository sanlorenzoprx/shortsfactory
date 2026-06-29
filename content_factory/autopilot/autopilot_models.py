from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


JsonDict = dict[str, Any]
AutopilotMode = Literal["dry_run", "supervised_autopilot", "full_autopilot"]


class AutopilotModelError(ValueError):
    pass


@dataclass(frozen=True)
class TrendSignal:
    trend_id: str
    source: str
    query: str
    topic: str
    market: str
    locale: str
    signal_strength: float
    velocity: str
    evidence: tuple[JsonDict, ...]
    captured_at: str

    def __post_init__(self) -> None:
        for name in ("trend_id", "source", "topic", "market", "locale", "captured_at"):
            if not str(getattr(self, name)).strip():
                raise AutopilotModelError(f"{name} is required")
        if not 0 <= self.signal_strength <= 1:
            raise AutopilotModelError("signal_strength must be between 0 and 1")
        if self.velocity not in {"rising", "stable", "falling", "unknown"}:
            raise AutopilotModelError("velocity is invalid")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "TrendSignal":
        return cls(**{**value, "evidence": tuple(value.get("evidence", []))})


@dataclass(frozen=True)
class BusinessIdeaCandidate:
    idea_id: str
    source_trend_id: str
    name: str
    description: str
    target_user: str
    market: str
    locale: str
    angle: str
    why_now: str
    constraints: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        for name in ("idea_id", "source_trend_id", "name", "description", "target_user", "market", "locale", "angle", "created_at"):
            if not str(getattr(self, name)).strip():
                raise AutopilotModelError(f"{name} is required")
        if len(self.description) < 40:
            raise AutopilotModelError("idea description must be specific")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "BusinessIdeaCandidate":
        return cls(**{**value, "constraints": tuple(value.get("constraints", []))})


@dataclass(frozen=True)
class VerdictRecord:
    idea_id: str
    verdict: JsonDict
    warning: str | None
    created_at: str

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "VerdictRecord":
        return cls(**value)


@dataclass(frozen=True)
class VerdictDecision:
    idea_id: str
    job_id: str | None
    lit_score: int
    risk_level: str
    decision: Literal["accept", "reject", "revise"]
    reason: str
    minimum_score: int
    required_fields_present: bool
    warnings: tuple[str, ...]
    created_at: str

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "VerdictDecision":
        return cls(**{**value, "warnings": tuple(value.get("warnings", []))})


@dataclass(frozen=True)
class GateResult:
    job_id: str
    gate_name: str
    status: Literal["pass", "fail", "warn"]
    blocking: bool
    reason: str
    source_artifacts: tuple[str, ...]
    created_at: str
    details: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "GateResult":
        return cls(**{**value, "source_artifacts": tuple(value.get("source_artifacts", []))})


@dataclass(frozen=True)
class PublishAttempt:
    publish_attempt_id: str
    batch_id: str
    job_id: str
    platform: str
    mode: str
    adapter: str
    status: str
    external_post_id: str | None
    external_url: str | None
    blocked_reason: str | None
    metadata_path: str
    created_at: str
    finished_at: str | None

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "PublishAttempt":
        return cls(**value)


@dataclass(frozen=True)
class AnalyticsSnapshot:
    snapshot_id: str
    batch_id: str
    job_id: str
    platform: str
    source: str
    metrics: dict[str, int]
    captured_at: str

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "AnalyticsSnapshot":
        return cls(**value)


@dataclass(frozen=True)
class LearningLoopRecommendation:
    batch_id: str
    status: str
    recommendation_type: str
    message: str
    next_trend_queries: tuple[str, ...]
    next_batch_size: int
    created_at: str

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "LearningLoopRecommendation":
        return cls(**{**value, "next_trend_queries": tuple(value.get("next_trend_queries", []))})
