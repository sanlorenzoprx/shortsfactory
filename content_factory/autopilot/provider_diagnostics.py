from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProviderContentDiagnostics:
    provider_http_status: int | None = None
    provider_selected_model: str | None = None
    provider_selected_provider: str | None = None
    provider_error_type: str | None = None
    content_present: bool = False
    content_length: int = 0
    content_starts_with_json: bool = False
    content_starts_with_markdown_fence: bool = False
    json_extraction_used: bool = False
    parse_error_type: str | None = None
    schema_error_type: str | None = None
    compact_schema_valid: bool = False
    internal_schema_valid: bool = False
    missing_required_fields: list[str] = field(default_factory=list)
    schema_error_count: int = 0
    quality_valid: bool = False
    quality_error_type: str | None = None
    quality_error_count: int = 0
    quality_failed_checks: list[str] = field(default_factory=list)
    quality_missing_fields: list[str] = field(default_factory=list)
    quality_duplicate_fields: list[str] = field(default_factory=list)
    angle_count: int = 0
    required_angle_ids_present: list[str] = field(default_factory=list)
    required_angle_ids_missing: list[str] = field(default_factory=list)
    cta_present: bool = False
    ghosttowntest_cta_present: bool = False
    longform_present: bool = False
    scripts_present_count: int = 0
    captions_present_count: int = 0
    thumbnail_text_present_count: int = 0
    hashtags_present_count: int = 0
    final_block_reason: str | None = None

    def record_content(self, content: str | None) -> None:
        trimmed = content.strip() if isinstance(content, str) else ""
        self.content_present = bool(trimmed)
        self.content_length = len(trimmed)
        self.content_starts_with_json = trimmed.startswith("{")
        self.content_starts_with_markdown_fence = trimmed.startswith("```")
        if not trimmed:
            self.record_parse_failure("empty_provider_content")

    def record_provider_failure(self, error_type: str) -> None:
        self.provider_error_type = error_type
        self.final_block_reason = error_type

    def record_schema_failure(self, error_type: str, paths: list[str]) -> None:
        self.schema_error_type = error_type
        self.missing_required_fields = sorted(set(paths))
        self.schema_error_count = len(paths)
        self.final_block_reason = error_type

    def record_parse_failure(self, error_type: str) -> None:
        self.parse_error_type = error_type
        self.final_block_reason = error_type

    def record_quality_result(
        self,
        *,
        quality_valid: bool,
        gates: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        required_angle_ids: list[str] | tuple[str, ...] | set[str],
        angle_ids: list[str] | tuple[str, ...],
        short_summaries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        longform_present: bool,
        longform_cta_present: bool,
        longform_ghosttowntest_cta_present: bool,
    ) -> None:
        required_order = list(required_angle_ids)
        present = [angle_id for angle_id in required_order if angle_id in set(angle_ids)]
        missing = [angle_id for angle_id in required_order if angle_id not in set(angle_ids)]
        duplicates = sorted({angle_id for angle_id in angle_ids if angle_ids.count(angle_id) > 1})
        failed_checks = [
            str(gate.get("gate_name"))
            for gate in gates
            if gate.get("blocking") is True and gate.get("status") == "fail" and gate.get("gate_name")
        ]
        missing_fields: list[str] = []
        scripts_present = 0
        captions_present = 0
        thumbnail_text_present = 0
        hashtags_present = 0
        cta_checks: list[bool] = []
        ghosttowntest_cta_checks: list[bool] = []
        for summary in short_summaries:
            angle_id = str(summary.get("angle_id", "unknown"))
            if summary.get("script_present"):
                scripts_present += 1
            else:
                missing_fields.append(f"$.shorts.{angle_id}.script")
            if summary.get("caption_present"):
                captions_present += 1
            else:
                missing_fields.append(f"$.shorts.{angle_id}.caption")
            if summary.get("thumbnail_text_present"):
                thumbnail_text_present += 1
            else:
                missing_fields.append(f"$.shorts.{angle_id}.thumbnail_text")
            if summary.get("hashtags_present"):
                hashtags_present += 1
            else:
                missing_fields.append(f"$.shorts.{angle_id}.hashtags")
            if not summary.get("cta_present"):
                missing_fields.append(f"$.shorts.{angle_id}.cta")
            cta_checks.append(bool(summary.get("cta_present")))
            short_ghosttowntest_cta_present = bool(summary.get("ghosttowntest_cta_present"))
            if not short_ghosttowntest_cta_present:
                missing_fields.append(f"$.shorts.{angle_id}.ghosttowntest_cta")
            ghosttowntest_cta_checks.append(short_ghosttowntest_cta_present)
        if not longform_present:
            missing_fields.append("$.longform")
        if not longform_cta_present:
            missing_fields.append("$.longform.cta_to_ghosttowntest_com")
        if not longform_ghosttowntest_cta_present:
            missing_fields.append("$.longform.ghosttowntest_cta")
        cta_checks.append(longform_cta_present)
        ghosttowntest_cta_checks.append(longform_ghosttowntest_cta_present)
        if duplicates:
            missing_fields.append("$.angles[].angle_id")
        self.quality_valid = quality_valid
        self.quality_failed_checks = failed_checks
        self.quality_error_count = len(failed_checks)
        self.quality_error_type = None if quality_valid else self._quality_error_type(failed_checks)
        self.quality_missing_fields = sorted(set(missing_fields))
        self.quality_duplicate_fields = [f"$.angles.{angle_id}" for angle_id in duplicates]
        self.angle_count = len(angle_ids)
        self.required_angle_ids_present = present
        self.required_angle_ids_missing = missing
        self.cta_present = bool(cta_checks) and all(cta_checks)
        self.ghosttowntest_cta_present = bool(ghosttowntest_cta_checks) and all(ghosttowntest_cta_checks)
        self.longform_present = longform_present
        self.scripts_present_count = scripts_present
        self.captions_present_count = captions_present
        self.thumbnail_text_present_count = thumbnail_text_present
        self.hashtags_present_count = hashtags_present
        if quality_valid:
            self.final_block_reason = None
        elif failed_checks:
            self.final_block_reason = "quality_invalid"

    @staticmethod
    def _quality_error_type(failed_checks: list[str]) -> str | None:
        if not failed_checks:
            return None
        mapping = {
            "exact_five_unique_angles": "required_angles_invalid",
            "lit_verdict_traceability": "lit_verdict_traceability_invalid",
            "five_complete_short_jobs": "missing_required_short_fields",
            "specific_hooks": "weak_or_mismatched_hooks",
            "buyer_pain_action_specificity": "missing_buyer_pain_action_specificity",
            "verdict_grounded_claims": "unsupported_claims",
            "ghost_town_cta": "missing_required_cta",
            "youtube_titles": "invalid_youtube_titles",
            "thumbnail_specificity": "invalid_thumbnail_text",
            "youtube_metadata_drafts": "invalid_youtube_metadata_drafts",
            "longform_assembly": "invalid_longform_assembly",
            "secret_redaction": "unsafe_generated_content",
            "no_platform_actions": "platform_action_requested",
            "publishing_closed": "publishing_gate_failed",
        }
        return mapping.get(failed_checks[0], "quality_gate_failed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
