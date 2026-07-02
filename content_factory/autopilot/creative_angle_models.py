from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .verdict_grounding import EXTERNAL_FACT_CATEGORIES, GROUNDING_PACKET_FIELDS


JsonDict = dict[str, Any]
SAFE_DIAGNOSTIC_ANGLE_IDS = {
    "ghost_town_risk",
    "buyer_reality",
    "fast_validation_test",
    "contrarian_opportunity",
    "builder_action_plan",
}
SAFE_BUYER_PAIN_ACTION_ERRORS = {
    None,
    "missing_buyer_signal",
    "missing_pain_signal",
    "missing_action_signal",
    "missing_buyer_pain_action_specificity",
}
SAFE_VERDICT_GROUNDING_ERRORS = {
    None,
    "missing_verdict_grounding",
    "generic_claim_signal",
    "external_fact_signal",
    "missing_idea_specificity",
    "missing_angle_specificity",
}
SAFE_HOOK_SPECIFICITY_ERRORS = {
    None,
    "generic_hook",
    "angle_mismatch_hook",
    "missing_verdict_signal",
    "missing_hook_specificity",
}
SAFE_EXTERNAL_FACT_ERRORS = {None, "external_fact_signal", *EXTERNAL_FACT_CATEGORIES}


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
    idea_summary: str | None = None
    verdict_summary: str | None = None

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
        for name in ("idea_summary", "verdict_summary"):
            value = getattr(self, name)
            if value is not None:
                _required(value, name)

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
    provider_reported_cost: float | None
    adapter_type: str | None
    five_angles_generated: bool
    short_jobs_created: int
    longform_plan_created: bool
    gates: tuple[JsonDict, ...]
    source_receipt_references: dict[str, str]
    secrets_recorded: bool
    network_called: bool
    raw_response_stored: bool
    reasoning_details_stored: bool
    stream_enabled: bool
    publish_attempted: bool
    youtube_api_called: bool
    videos_insert_called: bool
    schema_valid: bool
    provider_diagnostics: JsonDict
    redacted_error: str | None
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
        if self.reasoning_details_stored is not False:
            raise CreativeAngleContractError("receipts must not store LLM reasoning details")
        if self.stream_enabled is not False:
            raise CreativeAngleContractError("creative generation must not stream LLM responses")
        if self.publish_attempted is not False:
            raise CreativeAngleContractError("creative generation cannot publish")
        if self.youtube_api_called is not False or self.videos_insert_called is not False:
            raise CreativeAngleContractError("creative generation cannot call YouTube APIs")
        allowed_diagnostics = {
            "provider_http_status", "provider_selected_model", "provider_selected_provider",
            "provider_error_type",
            "content_present", "content_length", "content_starts_with_json",
            "content_starts_with_markdown_fence", "json_extraction_used", "parse_error_type",
            "json_parse_error_type", "json_parse_error_line", "json_parse_error_column",
            "json_parse_error_position", "extracted_json_length",
            "extracted_json_starts_with_object", "extracted_json_ends_with_object",
            "brace_balance_delta", "bracket_balance_delta", "quote_count_parity_even",
            "contains_control_characters", "likely_truncated", "multiple_json_objects_detected",
            "trailing_text_after_json_detected", "markdown_fence_detected", "parse_stage",
            "schema_error_type", "compact_schema_valid", "internal_schema_valid",
            "missing_required_fields", "schema_error_count", "quality_valid",
            "quality_error_type", "quality_error_count", "quality_failed_checks",
            "quality_missing_fields", "quality_duplicate_fields", "angle_count",
            "required_angle_ids_present", "required_angle_ids_missing", "cta_present",
            "ghosttowntest_cta_present", "longform_present", "scripts_present_count",
            "captions_present_count", "thumbnail_text_present_count", "hashtags_present_count",
            "buyer_pain_action_error_type", "buyer_pain_action_failed_angle_ids",
            "buyer_pain_action_passed_angle_ids", "buyer_signal_missing_count",
            "pain_signal_missing_count", "action_signal_missing_count",
            "buyer_pain_action_error_count",
            "verdict_grounding_error_type", "verdict_grounding_failed_angle_ids",
            "verdict_grounding_passed_angle_ids", "verdict_signal_missing_count",
            "generic_claim_signal_count", "external_fact_signal_count",
            "idea_specificity_missing_count", "angle_specificity_missing_count",
            "hook_specificity_error_type", "hook_specificity_failed_angle_ids",
            "hook_specificity_passed_angle_ids", "generic_hook_count",
            "angle_mismatch_hook_count", "verdict_signal_missing_hook_count",
            "grounding_packet_present", "grounding_packet_field_count",
            "grounding_packet_missing_fields", "grounding_terms_count",
            "target_buyer_terms_count", "pain_terms_count", "risk_terms_count",
            "validation_action_terms_count", "verdict_signal_terms_count",
            "opportunity_terms_count", "external_fact_error_type",
            "external_fact_failed_angle_ids", "external_fact_signal_categories",
            "external_fact_category_counts",
            "output_budget_tokens", "compact_prompt_budget_enabled",
            "expected_budget_profile", "truncation_risk_detected",
            "final_block_reason",
        }
        if set(self.provider_diagnostics) - allowed_diagnostics:
            raise CreativeAngleContractError("provider diagnostics contain unsafe fields")
        missing_paths = self.provider_diagnostics.get("missing_required_fields", [])
        if not isinstance(missing_paths, list) or any(
            not isinstance(path, str) or not path.startswith("$") for path in missing_paths
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe schema paths")
        quality_paths = self.provider_diagnostics.get("quality_missing_fields", [])
        if not isinstance(quality_paths, list) or any(
            not isinstance(path, str) or not path.startswith("$") for path in quality_paths
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe quality paths")
        duplicate_paths = self.provider_diagnostics.get("quality_duplicate_fields", [])
        if not isinstance(duplicate_paths, list) or any(
            not isinstance(path, str) or not path.startswith("$") for path in duplicate_paths
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe duplicate paths")
        for field_name in (
            "buyer_pain_action_failed_angle_ids",
            "buyer_pain_action_passed_angle_ids",
            "verdict_grounding_failed_angle_ids",
            "verdict_grounding_passed_angle_ids",
            "hook_specificity_failed_angle_ids",
            "hook_specificity_passed_angle_ids",
            "external_fact_failed_angle_ids",
        ):
            angle_ids = self.provider_diagnostics.get(field_name, [])
            if not isinstance(angle_ids, list) or any(
                angle_id not in SAFE_DIAGNOSTIC_ANGLE_IDS for angle_id in angle_ids
            ):
                raise CreativeAngleContractError("provider diagnostics contain unsafe angle IDs")
        if self.provider_diagnostics.get("buyer_pain_action_error_type") not in SAFE_BUYER_PAIN_ACTION_ERRORS:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe buyer pain action error")
        if self.provider_diagnostics.get("verdict_grounding_error_type") not in SAFE_VERDICT_GROUNDING_ERRORS:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe verdict grounding error")
        if self.provider_diagnostics.get("hook_specificity_error_type") not in SAFE_HOOK_SPECIFICITY_ERRORS:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe hook specificity error")
        if self.provider_diagnostics.get("external_fact_error_type") not in SAFE_EXTERNAL_FACT_ERRORS:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe external fact error")
        missing_packet_fields = self.provider_diagnostics.get("grounding_packet_missing_fields", [])
        if not isinstance(missing_packet_fields, list) or any(
            field_name not in GROUNDING_PACKET_FIELDS for field_name in missing_packet_fields
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe grounding packet fields")
        external_categories = self.provider_diagnostics.get("external_fact_signal_categories", [])
        if not isinstance(external_categories, list) or any(
            category not in EXTERNAL_FACT_CATEGORIES for category in external_categories
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe external fact categories")
        external_counts = self.provider_diagnostics.get("external_fact_category_counts", {})
        if not isinstance(external_counts, dict) or any(
            category not in EXTERNAL_FACT_CATEGORIES
            or not isinstance(count, int) or isinstance(count, bool) or count < 0
            for category, count in external_counts.items()
        ):
            raise CreativeAngleContractError("provider diagnostics contain unsafe external fact counts")
        output_budget = self.provider_diagnostics.get("output_budget_tokens", 0)
        if not isinstance(output_budget, int) or isinstance(output_budget, bool) or output_budget < 0:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe output budget")
        if self.provider_diagnostics.get("expected_budget_profile") not in {
            None, "compact_json_v1", "compact_angle_v1",
        }:
            raise CreativeAngleContractError("provider diagnostics contain an unsafe budget profile")
        for field_name in ("compact_prompt_budget_enabled", "truncation_risk_detected"):
            if not isinstance(self.provider_diagnostics.get(field_name, False), bool):
                raise CreativeAngleContractError("provider diagnostics contain an unsafe budget flag")
        for field_name in (
            "buyer_signal_missing_count",
            "pain_signal_missing_count",
            "action_signal_missing_count",
            "buyer_pain_action_error_count",
            "verdict_signal_missing_count",
            "generic_claim_signal_count",
            "external_fact_signal_count",
            "idea_specificity_missing_count",
            "angle_specificity_missing_count",
            "generic_hook_count",
            "angle_mismatch_hook_count",
            "verdict_signal_missing_hook_count",
            "grounding_packet_field_count",
            "grounding_terms_count",
            "target_buyer_terms_count",
            "pain_terms_count",
            "risk_terms_count",
            "validation_action_terms_count",
            "verdict_signal_terms_count",
            "opportunity_terms_count",
        ):
            count = self.provider_diagnostics.get(field_name, 0)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise CreativeAngleContractError("provider diagnostics contain an unsafe signal count")
        if self.provider_type == "online_llm" and self.status not in {"passed", "blocked", "failed"}:
            raise CreativeAngleContractError("online LLM receipt status must be passed, blocked, or failed")
        if self.safety.get("full_autopilot_enabled") is not False:
            raise CreativeAngleContractError("receipts cannot enable full_autopilot")
        if self.safety.get("supervised_autopilot_enabled") is not False:
            raise CreativeAngleContractError("receipts cannot enable supervised_autopilot")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: JsonDict) -> "CreativeAnglePackReceipt":
        return cls(**{
            "provider_reported_cost": None,
            "reasoning_details_stored": False,
            "stream_enabled": False,
            "provider_diagnostics": {},
            **value,
            "gates": tuple(value.get("gates", [])),
        })
