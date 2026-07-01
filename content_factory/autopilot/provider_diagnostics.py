from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .verdict_grounding import grounding_packet_diagnostics


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
    json_parse_error_type: str | None = None
    json_parse_error_line: int | None = None
    json_parse_error_column: int | None = None
    json_parse_error_position: int | None = None
    extracted_json_length: int = 0
    extracted_json_starts_with_object: bool = False
    extracted_json_ends_with_object: bool = False
    brace_balance_delta: int = 0
    bracket_balance_delta: int = 0
    quote_count_parity_even: bool = True
    contains_control_characters: bool = False
    likely_truncated: bool = False
    multiple_json_objects_detected: bool = False
    trailing_text_after_json_detected: bool = False
    markdown_fence_detected: bool = False
    parse_stage: str | None = None
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
    buyer_pain_action_error_type: str | None = None
    buyer_pain_action_failed_angle_ids: list[str] = field(default_factory=list)
    buyer_pain_action_passed_angle_ids: list[str] = field(default_factory=list)
    buyer_signal_missing_count: int = 0
    pain_signal_missing_count: int = 0
    action_signal_missing_count: int = 0
    buyer_pain_action_error_count: int = 0
    verdict_grounding_error_type: str | None = None
    verdict_grounding_failed_angle_ids: list[str] = field(default_factory=list)
    verdict_grounding_passed_angle_ids: list[str] = field(default_factory=list)
    verdict_signal_missing_count: int = 0
    generic_claim_signal_count: int = 0
    external_fact_signal_count: int = 0
    idea_specificity_missing_count: int = 0
    angle_specificity_missing_count: int = 0
    hook_specificity_error_type: str | None = None
    hook_specificity_failed_angle_ids: list[str] = field(default_factory=list)
    hook_specificity_passed_angle_ids: list[str] = field(default_factory=list)
    generic_hook_count: int = 0
    angle_mismatch_hook_count: int = 0
    verdict_signal_missing_hook_count: int = 0
    grounding_packet_present: bool = False
    grounding_packet_field_count: int = 0
    grounding_packet_missing_fields: list[str] = field(default_factory=list)
    grounding_terms_count: int = 0
    target_buyer_terms_count: int = 0
    pain_terms_count: int = 0
    risk_terms_count: int = 0
    validation_action_terms_count: int = 0
    verdict_signal_terms_count: int = 0
    opportunity_terms_count: int = 0
    external_fact_error_type: str | None = None
    external_fact_failed_angle_ids: list[str] = field(default_factory=list)
    external_fact_signal_categories: list[str] = field(default_factory=list)
    external_fact_category_counts: dict[str, int] = field(default_factory=dict)
    final_block_reason: str | None = None

    def record_content(self, content: str | None) -> None:
        trimmed = content.strip() if isinstance(content, str) else ""
        self.content_present = bool(trimmed)
        self.content_length = len(trimmed)
        self.content_starts_with_json = trimmed.startswith("{")
        self.content_starts_with_markdown_fence = trimmed.startswith("```")
        if not trimmed:
            self.parse_stage = "content_extraction"
            self.record_parse_failure("empty_provider_content")

    def record_provider_failure(self, error_type: str) -> None:
        self.provider_error_type = error_type
        self.final_block_reason = error_type

    def record_schema_failure(self, error_type: str, paths: list[str]) -> None:
        if error_type == "compact_schema_invalid":
            self.parse_error_type = None
            self.json_parse_error_type = None
            self.json_parse_error_line = None
            self.json_parse_error_column = None
            self.json_parse_error_position = None
            self.parse_stage = "compact_schema"
        self.schema_error_type = error_type
        self.missing_required_fields = sorted(set(paths))
        self.schema_error_count = len(paths)
        self.final_block_reason = error_type

    def record_parse_failure(self, error_type: str) -> None:
        self.parse_error_type = error_type
        self.final_block_reason = error_type

    def record_json_extraction(self, diagnostics: Any) -> None:
        for name in (
            "json_extraction_used", "parse_error_type", "json_parse_error_type",
            "json_parse_error_line", "json_parse_error_column", "json_parse_error_position",
            "extracted_json_length", "extracted_json_starts_with_object",
            "extracted_json_ends_with_object", "brace_balance_delta", "bracket_balance_delta",
            "quote_count_parity_even", "contains_control_characters", "likely_truncated",
            "multiple_json_objects_detected", "trailing_text_after_json_detected",
            "markdown_fence_detected", "parse_stage",
        ):
            setattr(self, name, getattr(diagnostics, name))
        if self.parse_error_type is not None:
            self.final_block_reason = self.parse_error_type

    def record_grounding_packet(self, packet: dict[str, Any]) -> None:
        for name, value in grounding_packet_diagnostics(packet).items():
            setattr(self, name, value)

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
        buyer_pain_action_failed: list[str] = []
        buyer_pain_action_passed: list[str] = []
        buyer_missing = 0
        pain_missing = 0
        action_missing = 0
        verdict_grounding_failed: list[str] = []
        verdict_grounding_passed: list[str] = []
        verdict_signal_missing = 0
        generic_claim_signals = 0
        external_fact_signals = 0
        idea_specificity_missing = 0
        angle_specificity_missing = 0
        hook_specificity_failed: list[str] = []
        hook_specificity_passed: list[str] = []
        generic_hooks = 0
        angle_mismatch_hooks = 0
        verdict_signal_missing_hooks = 0
        external_fact_failed: list[str] = []
        external_fact_categories: set[str] = set()
        external_fact_category_counts: dict[str, int] = {}
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
            buyer_present = bool(summary.get("buyer_signal_present"))
            pain_present = bool(summary.get("pain_signal_present"))
            action_present = bool(summary.get("action_signal_present"))
            buyer_missing += int(not buyer_present)
            pain_missing += int(not pain_present)
            action_missing += int(not action_present)
            if buyer_present and pain_present and action_present:
                buyer_pain_action_passed.append(angle_id)
            else:
                buyer_pain_action_failed.append(angle_id)
            verdict_present = bool(summary.get("verdict_signal_present"))
            generic_claim = bool(summary.get("generic_claim_signal_present"))
            external_fact = bool(summary.get("external_fact_signal_present"))
            angle_external_categories = summary.get("external_fact_signal_categories", [])
            angle_external_categories = (
                angle_external_categories if isinstance(angle_external_categories, list) else []
            )
            idea_specific = bool(summary.get("idea_specificity_present"))
            angle_specific = bool(summary.get("angle_specificity_present"))
            verdict_signal_missing += int(not verdict_present)
            generic_claim_signals += int(generic_claim)
            external_fact_signals += int(external_fact)
            if angle_external_categories:
                external_fact_failed.append(angle_id)
            for category in angle_external_categories:
                if not isinstance(category, str):
                    continue
                external_fact_categories.add(category)
                external_fact_category_counts[category] = external_fact_category_counts.get(category, 0) + 1
            idea_specificity_missing += int(not idea_specific)
            angle_specificity_missing += int(not angle_specific)
            if verdict_present and not generic_claim and not external_fact and idea_specific and angle_specific:
                verdict_grounding_passed.append(angle_id)
            else:
                verdict_grounding_failed.append(angle_id)
            generic_hook = bool(summary.get("hook_generic"))
            angle_mismatch_hook = not bool(summary.get("hook_angle_match"))
            verdict_missing_hook = not bool(summary.get("hook_verdict_signal_present"))
            generic_hooks += int(generic_hook)
            angle_mismatch_hooks += int(angle_mismatch_hook)
            verdict_signal_missing_hooks += int(verdict_missing_hook)
            if not generic_hook and not angle_mismatch_hook and not verdict_missing_hook:
                hook_specificity_passed.append(angle_id)
            else:
                hook_specificity_failed.append(angle_id)
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
        self.buyer_pain_action_failed_angle_ids = buyer_pain_action_failed
        self.buyer_pain_action_passed_angle_ids = buyer_pain_action_passed
        self.buyer_signal_missing_count = buyer_missing
        self.pain_signal_missing_count = pain_missing
        self.action_signal_missing_count = action_missing
        self.buyer_pain_action_error_count = len(buyer_pain_action_failed)
        self.buyer_pain_action_error_type = self._buyer_pain_action_error_type(
            buyer_missing=buyer_missing,
            pain_missing=pain_missing,
            action_missing=action_missing,
            failed_count=len(buyer_pain_action_failed),
        )
        self.verdict_grounding_failed_angle_ids = verdict_grounding_failed
        self.verdict_grounding_passed_angle_ids = verdict_grounding_passed
        self.verdict_signal_missing_count = verdict_signal_missing
        self.generic_claim_signal_count = generic_claim_signals
        self.external_fact_signal_count = external_fact_signals
        self.idea_specificity_missing_count = idea_specificity_missing
        self.angle_specificity_missing_count = angle_specificity_missing
        self.verdict_grounding_error_type = self._verdict_grounding_error_type(
            failed_count=len(verdict_grounding_failed),
            verdict_signal_missing=verdict_signal_missing,
            generic_claim_signals=generic_claim_signals,
            external_fact_signals=external_fact_signals,
            idea_specificity_missing=idea_specificity_missing,
            angle_specificity_missing=angle_specificity_missing,
        )
        self.hook_specificity_failed_angle_ids = hook_specificity_failed
        self.hook_specificity_passed_angle_ids = hook_specificity_passed
        self.generic_hook_count = generic_hooks
        self.angle_mismatch_hook_count = angle_mismatch_hooks
        self.verdict_signal_missing_hook_count = verdict_signal_missing_hooks
        self.hook_specificity_error_type = self._hook_specificity_error_type(
            failed_count=len(hook_specificity_failed),
            generic_hooks=generic_hooks,
            angle_mismatch_hooks=angle_mismatch_hooks,
            verdict_signal_missing_hooks=verdict_signal_missing_hooks,
        )
        self.external_fact_failed_angle_ids = external_fact_failed
        self.external_fact_signal_categories = sorted(external_fact_categories)
        self.external_fact_category_counts = {
            category: external_fact_category_counts[category]
            for category in sorted(external_fact_category_counts)
        }
        self.external_fact_error_type = (
            None
            if not external_fact_categories
            else next(iter(external_fact_categories))
            if len(external_fact_categories) == 1
            else "external_fact_signal"
        )
        self.quality_error_type = None if quality_valid else self._quality_error_type(
            failed_checks,
            buyer_pain_action_error_type=self.buyer_pain_action_error_type,
            verdict_grounding_error_type=self.verdict_grounding_error_type,
            hook_specificity_error_type=self.hook_specificity_error_type,
        )
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
    def _quality_error_type(
        failed_checks: list[str], *, buyer_pain_action_error_type: str | None = None,
        verdict_grounding_error_type: str | None = None,
        hook_specificity_error_type: str | None = None,
    ) -> str | None:
        if not failed_checks:
            return None
        if "verdict_grounded_claims" in failed_checks and verdict_grounding_error_type:
            return "missing_verdict_grounding"
        if "specific_hooks" in failed_checks and hook_specificity_error_type:
            return "missing_hook_specificity"
        if "buyer_pain_action_specificity" in failed_checks and buyer_pain_action_error_type:
            return buyer_pain_action_error_type
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

    @staticmethod
    def _buyer_pain_action_error_type(
        *, buyer_missing: int, pain_missing: int, action_missing: int, failed_count: int,
    ) -> str | None:
        if failed_count == 0:
            return None
        missing_types = sum(count > 0 for count in (buyer_missing, pain_missing, action_missing))
        if missing_types == 1:
            if buyer_missing:
                return "missing_buyer_signal"
            if pain_missing:
                return "missing_pain_signal"
            return "missing_action_signal"
        return "missing_buyer_pain_action_specificity"

    @staticmethod
    def _verdict_grounding_error_type(
        *, failed_count: int, verdict_signal_missing: int, generic_claim_signals: int,
        external_fact_signals: int, idea_specificity_missing: int, angle_specificity_missing: int,
    ) -> str | None:
        if failed_count == 0:
            return None
        if generic_claim_signals:
            return "generic_claim_signal"
        if external_fact_signals:
            return "external_fact_signal"
        if verdict_signal_missing:
            return "missing_verdict_grounding"
        if idea_specificity_missing:
            return "missing_idea_specificity"
        if angle_specificity_missing:
            return "missing_angle_specificity"
        return "missing_verdict_grounding"

    @staticmethod
    def _hook_specificity_error_type(
        *, failed_count: int, generic_hooks: int, angle_mismatch_hooks: int,
        verdict_signal_missing_hooks: int,
    ) -> str | None:
        if failed_count == 0:
            return None
        failure_types = sum(count > 0 for count in (
            generic_hooks, angle_mismatch_hooks, verdict_signal_missing_hooks,
        ))
        if failure_types == 1:
            if generic_hooks:
                return "generic_hook"
            if angle_mismatch_hooks:
                return "angle_mismatch_hook"
            return "missing_verdict_signal"
        return "missing_hook_specificity"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
