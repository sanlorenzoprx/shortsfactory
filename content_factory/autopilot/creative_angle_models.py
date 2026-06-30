from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


class CreativeAngleContractError(ValueError):
    pass


def _required(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CreativeAngleContractError(f"{name} is required")


@dataclass(frozen=True)
class CreativeAngleSpec:
    angle_id: str
    angle_name: str
    purpose: str
    hook_style: str
    target_emotion: str
    viewer_question: str
    expected_behavior_signal: str

    def __post_init__(self) -> None:
        for name in (
            "angle_id", "angle_name", "purpose", "hook_style", "target_emotion",
            "viewer_question", "expected_behavior_signal",
        ):
            _required(getattr(self, name), name)

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "CreativeAngleSpec":
        return cls(**value)


@dataclass(frozen=True)
class CreativeAnglePack:
    angle_pack_id: str
    idea_id: str
    trend_id: str | None
    lit_verdict_id: str
    rubric_version: str
    provider_type: str
    model_id: str | None
    prompt_prefix_hash: str
    input_hash: str
    output_hash: str
    angles: tuple[CreativeAngleSpec, ...]

    def __post_init__(self) -> None:
        for name in (
            "angle_pack_id", "idea_id", "lit_verdict_id", "rubric_version",
            "provider_type", "prompt_prefix_hash", "input_hash", "output_hash",
        ):
            _required(getattr(self, name), name)
        if len(self.angles) != 5:
            raise CreativeAngleContractError("a creative angle pack must contain exactly five angles")
        if len({angle.angle_id for angle in self.angles}) != 5:
            raise CreativeAngleContractError("creative angle IDs must be unique")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "CreativeAnglePack":
        return cls(
            **{
                **value,
                "angles": tuple(CreativeAngleSpec.from_dict(row) for row in value.get("angles", [])),
            }
        )


@dataclass(frozen=True)
class AngleShortJob:
    job_id: str
    angle_pack_id: str
    angle_id: str
    idea_id: str
    lit_verdict_id: str
    title: str
    hook: str
    script: str
    caption: str
    thumbnail_text: str
    cta: str
    tags: tuple[str, ...]
    hashtags: tuple[str, ...]
    youtube_metadata_draft: JsonDict
    source_receipt_references: dict[str, str]
    youtube_video_id: str | None = None
    upload_attempt_id: str | None = None
    verification_receipt: str | None = None
    analytics_receipt: str | None = None
    country_analytics_receipt: str | None = None
    performance_score: float | None = None
    data_quality: str = "pending"
    status: str = "creative_draft_ready"
    live_publish_enabled: bool = False

    def __post_init__(self) -> None:
        for name in (
            "job_id", "angle_pack_id", "angle_id", "idea_id", "lit_verdict_id",
            "title", "hook", "script", "caption", "thumbnail_text", "cta", "data_quality",
        ):
            _required(getattr(self, name), name)
        if not self.tags or not self.hashtags:
            raise CreativeAngleContractError("short jobs require tags and hashtags")
        if not self.source_receipt_references:
            raise CreativeAngleContractError("source receipt references are required")
        if self.youtube_metadata_draft.get("angle_id") != self.angle_id:
            raise CreativeAngleContractError("YouTube metadata angle_id must match the short")
        if self.youtube_metadata_draft.get("cta") != self.cta:
            raise CreativeAngleContractError("YouTube metadata CTA must match the short")
        if self.live_publish_enabled is not False:
            raise CreativeAngleContractError("short jobs cannot enable live publishing")

    def to_dict(self) -> JsonDict:
        value = asdict(self)
        value["tags"] = list(self.tags)
        value["hashtags"] = list(self.hashtags)
        return value

    @classmethod
    def from_dict(cls, value: JsonDict) -> "AngleShortJob":
        return cls(
            **{
                **value,
                "tags": tuple(value.get("tags", [])),
                "hashtags": tuple(value.get("hashtags", [])),
            }
        )


@dataclass(frozen=True)
class LongFormAssemblyPlan:
    longform_id: str
    angle_pack_id: str
    longform_title: str
    intro_script: str
    ordered_chapters: tuple[JsonDict, ...]
    transition_lines: tuple[str, ...]
    conclusion: str
    cta_to_ghosttowntest_com: str
    suggested_description: str
    suggested_chapters_timestamps: tuple[JsonDict, ...]
    source_short_job_ids: tuple[str, ...]
    status: str = "assembly_plan_ready"
    live_publish_enabled: bool = False

    def __post_init__(self) -> None:
        for name in (
            "longform_id", "angle_pack_id", "longform_title", "intro_script",
            "conclusion", "cta_to_ghosttowntest_com", "suggested_description",
        ):
            _required(getattr(self, name), name)
        if len(self.ordered_chapters) != 5 or len(self.source_short_job_ids) != 5:
            raise CreativeAngleContractError("long-form assembly must include all five source shorts")
        if len(set(self.source_short_job_ids)) != 5:
            raise CreativeAngleContractError("long-form source short IDs must be unique")
        if [chapter.get("job_id") for chapter in self.ordered_chapters] != list(self.source_short_job_ids):
            raise CreativeAngleContractError("chapter order must match the source short order")
        if len(self.transition_lines) != 4:
            raise CreativeAngleContractError("five chapters require four transition lines")
        if len(self.suggested_chapters_timestamps) != 6:
            raise CreativeAngleContractError("timestamps must include the intro and five chapters")
        if "GhostTownTest.com" not in self.cta_to_ghosttowntest_com:
            raise CreativeAngleContractError("long-form CTA must reference GhostTownTest.com")
        if self.live_publish_enabled is not False:
            raise CreativeAngleContractError("long-form plans cannot enable live publishing")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "LongFormAssemblyPlan":
        return cls(
            **{
                **value,
                "ordered_chapters": tuple(value.get("ordered_chapters", [])),
                "transition_lines": tuple(value.get("transition_lines", [])),
                "suggested_chapters_timestamps": tuple(value.get("suggested_chapters_timestamps", [])),
                "source_short_job_ids": tuple(value.get("source_short_job_ids", [])),
            }
        )


@dataclass(frozen=True)
class CreativeAnglePackReceipt:
    receipt_version: str
    timestamp: str
    angle_pack_id: str
    provider_type: str
    model_id: str | None
    model_provider: str | None
    model_profile_hash: str | None
    prompt_prefix_hash: str
    input_hash: str
    output_hash: str
    tokens_used: int | None
    cost_estimate: float | None
    estimated_input_tokens: int | None
    estimated_output_tokens: int | None
    estimated_cost: float | None
    adapter_type: str | None
    five_angles_generated: bool
    short_jobs_created: int
    longform_plan_created: bool
    gates: tuple[JsonDict, ...]
    source_receipt_references: dict[str, str]
    secrets_recorded: bool
    network_called: bool
    raw_response_stored: bool
    publish_attempted: bool
    status: str
    artifacts: dict[str, str] = field(default_factory=dict)
    safety: JsonDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "receipt_version", "timestamp", "angle_pack_id", "provider_type",
            "prompt_prefix_hash", "input_hash", "output_hash", "status",
        ):
            _required(getattr(self, name), name)
        if self.secrets_recorded is not False:
            raise CreativeAngleContractError("receipts must not record secrets")
        if self.raw_response_stored is not False:
            raise CreativeAngleContractError("receipts must not store raw LLM responses")
        if self.publish_attempted is not False:
            raise CreativeAngleContractError("creative generation cannot publish")
        if self.safety.get("full_autopilot_enabled") is not False:
            raise CreativeAngleContractError("receipts cannot enable full_autopilot")
        if self.safety.get("supervised_autopilot_enabled") is not False:
            raise CreativeAngleContractError("receipts cannot enable supervised_autopilot")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "CreativeAnglePackReceipt":
        return cls(**{**value, "gates": tuple(value.get("gates", []))})
