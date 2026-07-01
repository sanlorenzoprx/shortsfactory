from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .creative_angle_models import CreativeAnglePackReceipt
from .creative_angle_pack import CreativeAnglePackGenerator
from .creative_providers import OnlineLLMCreativeGenerationProvider
from .llm_model_registry import LLMFallbackGroup, LLMModelProfile, LLMModelRegistry
from .llm_provider_adapters import LLMAdapterError, LLMProviderAdapter, build_llm_adapter


FALLBACK_RECEIPT_VERSION = "phase5b.5b.openrouter-fallback.v1"
FATAL_GATE_NAMES = {"secret_redaction", "no_platform_actions", "publishing_closed"}
STAGE_RANK = {
    "network_failed": 0,
    "provider_rate_limited": 1,
    "empty_provider_content": 2,
    "malformed_json": 3,
    "compact_schema_invalid": 4,
    "internal_schema_invalid": 5,
    "quality_invalid": 6,
    "passed": 7,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".fallback.", suffix=".tmp", dir=path.parent)
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


class CreativeFallbackRunner:
    def __init__(
        self,
        *,
        registry: LLMModelRegistry,
        fallback_group_id: str,
        output_root: str | Path = "output",
        adapter_factory: Callable[[LLMModelProfile], LLMProviderAdapter] | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.registry = registry
        self.group, self.profiles = registry.require_fallback_group(fallback_group_id)
        self.output_root = Path(output_root).expanduser().resolve()
        self.adapter_factory = adapter_factory or self._live_adapter
        self.now = now

    @staticmethod
    def _live_adapter(profile: LLMModelProfile) -> LLMProviderAdapter:
        return build_llm_adapter(profile, allow_network=True, require_config=True)

    def run(
        self,
        *,
        idea_id: str | None = None,
        batch_id: str | None = None,
        lit_verdict_file: str | Path | None = None,
    ) -> tuple[dict[str, Any], Path, CreativeAnglePackReceipt | None, CreativeAnglePackGenerator | None]:
        timestamp = self.now().astimezone(timezone.utc).isoformat()
        fallback_attempt_id = "fba_" + hashlib.sha256(
            f"{self.group.fallback_group_id}|{timestamp}|{idea_id}|{lit_verdict_file}".encode("utf-8")
        ).hexdigest()[:12]
        path = self.fallback_receipt_path(fallback_attempt_id)
        relative_path = path.relative_to(self.output_root).as_posix()
        attempts: list[dict[str, Any]] = []
        selected_receipt: CreativeAnglePackReceipt | None = None
        selected_generator: CreativeAnglePackGenerator | None = None
        configuration_error: str | None = None

        try:
            adapters = tuple(self.adapter_factory(profile) for profile in self.profiles)
        except LLMAdapterError as exc:
            adapters = ()
            configuration_error = f"{type(exc).__name__}: fallback configuration refused"

        for profile, adapter in zip(self.profiles, adapters):
            provider = OnlineLLMCreativeGenerationProvider(profile, adapter)
            generator = CreativeAnglePackGenerator(
                provider=provider,
                output_root=self.output_root,
                now=self.now,
                online_provider_explicit=True,
                fallback_attempt=True,
                additional_source_receipt_references={"fallback_attempt_receipt": relative_path},
            )
            receipt = generator.generate(
                idea_id=idea_id,
                batch_id=batch_id,
                lit_verdict_file=lit_verdict_file,
            )
            attempt = self._attempt_summary(profile, generator, receipt, len(attempts) + 1)
            attempts.append(attempt)
            if receipt.status == "passed":
                selected_receipt = receipt
                selected_generator = generator
            current = self._receipt(
                fallback_attempt_id=fallback_attempt_id,
                timestamp=timestamp,
                attempts=attempts,
                selected_receipt=selected_receipt,
                configuration_error=configuration_error,
            )
            _atomic_json(path, current)
            if selected_receipt is not None or self._is_fatal(receipt):
                break

        result = self._receipt(
            fallback_attempt_id=fallback_attempt_id,
            timestamp=timestamp,
            attempts=attempts,
            selected_receipt=selected_receipt,
            configuration_error=configuration_error,
        )
        _atomic_json(path, result)
        return result, path, selected_receipt, selected_generator

    def fallback_receipt_path(self, fallback_attempt_id: str) -> Path:
        return self.output_root / "creative_angle_fallbacks" / fallback_attempt_id / "FALLBACK_ATTEMPT_RECEIPT.json"

    @staticmethod
    def _attempt_summary(
        profile: LLMModelProfile,
        generator: CreativeAnglePackGenerator,
        receipt: CreativeAnglePackReceipt,
        number: int,
    ) -> dict[str, Any]:
        diagnostics = dict(receipt.provider_diagnostics)
        stage = CreativeFallbackRunner._stage_reached(receipt, diagnostics)
        return {
            "attempt_number": number,
            "model_id": profile.model_id,
            "provider_model": profile.provider_model,
            "status": receipt.status,
            "schema_valid": receipt.schema_valid,
            "quality_valid": receipt.status == "passed",
            "stage_reached": stage,
            "final_block_reason": None if stage == "passed" else stage,
            "receipt": generator.receipt_path(receipt.angle_pack_id).relative_to(generator.output_root).as_posix(),
            "tokens_used": receipt.tokens_used,
            "cost_estimate": receipt.cost_estimate,
            "provider_reported_cost": receipt.provider_reported_cost,
            "network_called": receipt.network_called,
            "publish_attempted": False,
            "youtube_api_called": False,
            "videos_insert_called": False,
            "secrets_recorded": False,
            "raw_response_stored": False,
            "reasoning_details_stored": False,
            "stream_enabled": False,
            "provider_diagnostics": diagnostics,
        }

    @staticmethod
    def _is_fatal(receipt: CreativeAnglePackReceipt) -> bool:
        return any(
            gate.get("gate_name") in FATAL_GATE_NAMES and gate.get("status") == "fail"
            for gate in receipt.gates
        )

    def _receipt(
        self,
        *,
        fallback_attempt_id: str,
        timestamp: str,
        attempts: list[dict[str, Any]],
        selected_receipt: CreativeAnglePackReceipt | None,
        configuration_error: str | None,
    ) -> dict[str, Any]:
        selected_profile = (
            next((profile for profile in self.profiles if profile.model_id == selected_receipt.model_id), None)
            if selected_receipt is not None else None
        )
        numeric_tokens = [row["tokens_used"] for row in attempts if isinstance(row["tokens_used"], int)]
        numeric_costs = [row["cost_estimate"] for row in attempts if isinstance(row["cost_estimate"], (int, float))]
        reported_costs = [
            row["provider_reported_cost"] for row in attempts
            if isinstance(row["provider_reported_cost"], (int, float))
        ]
        diagnostics = (
            dict(selected_receipt.provider_diagnostics)
            if selected_receipt is not None
            else dict(attempts[-1]["provider_diagnostics"]) if attempts else {}
        )
        best_attempt = self._best_attempt(attempts)
        final_block_reason = None if selected_receipt is not None else (
            "configuration_error"
            if configuration_error and not attempts
            else best_attempt.get("stage_reached") if best_attempt else None
        )
        return {
            "receipt_version": FALLBACK_RECEIPT_VERSION,
            "timestamp": timestamp,
            "fallback_attempt_id": fallback_attempt_id,
            "fallback_group_id": self.group.fallback_group_id,
            "status": "passed" if selected_receipt is not None else "blocked",
            "final_block_reason": final_block_reason,
            "best_attempt_number": best_attempt.get("attempt_number") if best_attempt else None,
            "best_attempt_model_id": best_attempt.get("model_id") if best_attempt else None,
            "best_attempt_provider_model": best_attempt.get("provider_model") if best_attempt else None,
            "best_attempt_stage_reached": best_attempt.get("stage_reached") if best_attempt else None,
            "selected_model_id": selected_receipt.model_id if selected_receipt is not None else None,
            "selected_provider_model": selected_profile.provider_model if selected_profile is not None else None,
            "selected_angle_pack_id": selected_receipt.angle_pack_id if selected_receipt is not None else None,
            "total_attempts": len(attempts),
            "attempts": attempts,
            "tokens_used": sum(numeric_tokens) if numeric_tokens else None,
            "cost_estimate": round(sum(numeric_costs), 8) if numeric_costs else None,
            "provider_reported_cost": round(sum(reported_costs), 8) if reported_costs else None,
            "network_called": any(row["network_called"] for row in attempts),
            "publish_attempted": False,
            "youtube_api_called": False,
            "videos_insert_called": False,
            "secrets_recorded": False,
            "raw_response_stored": False,
            "reasoning_details_stored": False,
            "stream_enabled": False,
            "provider_diagnostics": diagnostics,
            **diagnostics,
            "final_block_reason": final_block_reason,
            "configuration_error": configuration_error,
        }

    @staticmethod
    def _best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not attempts:
            return None
        return max(
            attempts,
            key=lambda row: (STAGE_RANK.get(str(row.get("stage_reached")), -1), -int(row.get("attempt_number", 0))),
        )

    @staticmethod
    def _stage_reached(receipt: CreativeAnglePackReceipt, diagnostics: dict[str, Any]) -> str:
        if receipt.status == "passed":
            return "passed"
        if diagnostics.get("final_block_reason") == "quality_invalid" or diagnostics.get("quality_error_type"):
            return "quality_invalid"
        if diagnostics.get("schema_error_type") == "internal_schema_invalid":
            return "internal_schema_invalid"
        if diagnostics.get("schema_error_type") == "compact_schema_invalid":
            return "compact_schema_invalid"
        if diagnostics.get("provider_error_type") == "rate_limited":
            return "provider_rate_limited"
        if diagnostics.get("parse_error_type") == "empty_provider_content":
            return "empty_provider_content"
        if diagnostics.get("parse_error_type") in {
            "malformed_json", "json_object_not_found", "unsafe_provider_content",
        }:
            return "malformed_json"
        if diagnostics.get("provider_error_type") in {"provider_unavailable", "timeout", "network_failed"}:
            return "network_failed"
        if receipt.schema_valid is True and receipt.status != "passed":
            return "quality_invalid"
        return "network_failed"
