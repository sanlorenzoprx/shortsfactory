from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from content_factory.compliance import ComplianceChecklistError, load_compliance_checklist
from content_factory.exporting.manifest import read_export_manifest
from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within
from content_factory.previews import PreviewCardError, load_preview_manifest
from content_factory.quality.quality_store import QualityStore, QualityStoreError
from content_factory.upload_kits.kit_builder import UploadKitError, load_upload_kit_preview

from .result_models import ALLOWED_PLATFORMS, METRIC_FIELDS, SAFETY_FLAGS


class ResultsValidationError(RuntimeError):
    """Safe refusal while validating local results ledger entries."""


def validate_platform(platform: str) -> str:
    value = str(platform).strip()
    if value not in ALLOWED_PLATFORMS:
        raise ResultsValidationError(f"unsupported platform: {value}")
    return value


def validate_url(url: str) -> str:
    value = str(url).strip()
    if not value:
        raise ResultsValidationError("manual upload URL is required")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ResultsValidationError("manual upload URL must be https://...")
    return value


def validate_metrics(metrics: dict[str, Any]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for field in METRIC_FIELDS:
        raw = metrics.get(field, 0)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ResultsValidationError(f"{field} must be a non-negative integer") from exc
        if value < 0:
            raise ResultsValidationError(f"{field} must be a non-negative integer")
        normalized[field] = value
    return normalized


def _read_json(path: Path, label: str, root: Path) -> dict[str, Any]:
    if not path.is_file() or not is_within(path, root):
        raise ResultsValidationError(f"{label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResultsValidationError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise ResultsValidationError(f"{label} must be a JSON object")
    return value


def _template_context(receipt: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    ids: dict[str, str] = {}
    hashes: dict[str, str] = {}
    templates = receipt.get("templates", {})
    if not isinstance(templates, dict):
        return ids, hashes
    for key in ("script", "caption", "thumbnail"):
        value = templates.get(key)
        if not isinstance(value, dict):
            continue
        template_id = value.get("template_id")
        template_hash = value.get("template_version_hash")
        if isinstance(template_id, str) and template_id:
            ids[key] = template_id
        if isinstance(template_hash, str) and template_hash:
            hashes[key] = template_hash
    return ids, hashes


def validate_ready_job(
    job_id: str,
    *,
    export_root: str | Path = "exports",
    output_root: str | Path = "output",
) -> dict[str, Any]:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise ResultsValidationError("invalid job_id") from exc
    export_root_path = Path(export_root).expanduser().resolve()
    output_root_path = Path(output_root).expanduser().resolve()

    export_manifest = read_export_manifest(export_root_path, safe_id)
    if export_manifest is None:
        raise ResultsValidationError(f"approved export bundle is missing for job {safe_id}")
    if export_manifest.get("publishing_status") != "not_published":
        raise ResultsValidationError("approved export bundle is not safe for manual results")
    if export_manifest.get("live_publishing_enabled") is not False:
        raise ResultsValidationError("approved export bundle must keep live publishing disabled")

    try:
        upload_kit_preview = load_upload_kit_preview(export_root_path, safe_id)
    except UploadKitError as exc:
        raise ResultsValidationError(str(exc)) from exc
    if upload_kit_preview is None:
        raise ResultsValidationError(f"manual upload kit is missing for job {safe_id}")

    try:
        preview_manifest = load_preview_manifest(export_root_path, safe_id)
    except PreviewCardError as exc:
        raise ResultsValidationError(str(exc)) from exc
    if preview_manifest is None:
        raise ResultsValidationError(f"preview manifest is missing for job {safe_id}")

    try:
        compliance = load_compliance_checklist(export_root_path, safe_id)
    except ComplianceChecklistError as exc:
        raise ResultsValidationError(str(exc)) from exc
    if compliance is None or compliance.get("ready_for_manual_upload") is not True:
        raise ResultsValidationError(
            "Run compliance_check.py and mark reviewed before recording manual upload results."
        )

    receipt = _read_json(
        export_root_path / "approved" / safe_id / "receipt.json",
        "receipt.json",
        export_root_path,
    )
    if receipt.get("job_id") != safe_id:
        raise ResultsValidationError("receipt.json does not match job")

    try:
        quality = QualityStore(output_root_path).read(safe_id)
    except QualityStoreError as exc:
        raise ResultsValidationError(str(exc)) from exc

    template_ids, template_hashes = _template_context(receipt)
    return {
        "job_id": safe_id,
        "export_manifest": export_manifest,
        "upload_kit_preview": upload_kit_preview,
        "preview_manifest": preview_manifest,
        "compliance": compliance,
        "quality": quality,
        "receipt": receipt,
        "template_ids": template_ids,
        "template_hashes": template_hashes,
        "safety": dict(SAFETY_FLAGS),
    }
