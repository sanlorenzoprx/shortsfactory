from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within
from content_factory.previews import PreviewCardError, load_preview_manifest
from content_factory.previews.preview_models import PLATFORM_ORDER
from content_factory.upload_kits.manifest import (
    SAFETY_FIELDS,
    UploadKitManifestError,
    kit_directory,
    read_upload_kit_manifest,
)

from .compliance_models import (
    HUMAN_REVIEW_ITEMS,
    JSON_NAME,
    MARKDOWN_NAME,
    SAFETY_FLAGS,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
    ComplianceResult,
)
from .compliance_renderer import machine_status, render_markdown
from .compliance_rules import hashtag_tokens, platform_copy_warnings, text_warning_checks
from .compliance_store import (
    ComplianceStoreError,
    compliance_directory,
    load_checklist,
    write_checklist,
)


class ComplianceChecklistError(RuntimeError):
    """Safe refusal while generating or confirming local compliance."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, label: str, root: Path) -> dict[str, Any]:
    if not path.is_file() or not is_within(path, root):
        raise ComplianceChecklistError(f"{label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComplianceChecklistError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise ComplianceChecklistError(f"{label} must be a JSON object")
    return value


def _read_text(path: Path, label: str, root: Path) -> str:
    if not path.is_file() or not is_within(path, root):
        raise ComplianceChecklistError(f"{label} is missing")
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ComplianceChecklistError(f"{label} is unreadable") from exc


def _require_safety(value: dict[str, Any], label: str) -> None:
    for key, expected in SAFETY_FLAGS.items():
        if value.get(key) != expected:
            rendered = json.dumps(expected)
            raise ComplianceChecklistError(f"{label} must state {key}: {rendered}")


def _approved_export(export_root: Path, job_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], Path, Path | None]:
    directory = export_root / "approved" / job_id
    if not directory.is_dir() or not is_within(directory, export_root):
        raise ComplianceChecklistError(f"approved export bundle is missing for job {job_id}")
    approval = _read_json(directory / "APPROVAL.json", "APPROVAL.json", export_root)
    if approval.get("job_id") != job_id or approval.get("state") != "approved":
        raise ComplianceChecklistError(f"export bundle is not approved for job {job_id}")
    manifest = _read_json(directory / "EXPORT_MANIFEST.json", "EXPORT_MANIFEST.json", export_root)
    if manifest.get("job_id") != job_id:
        raise ComplianceChecklistError("export manifest does not match job")
    if manifest.get("publishing_status") != "not_published":
        raise ComplianceChecklistError("export manifest must state publishing_status: not_published")
    if manifest.get("live_publishing_enabled") is not False:
        raise ComplianceChecklistError("export manifest must state live_publishing_enabled: false")
    video = directory / "final.mp4"
    if not video.is_file() or not is_within(video, export_root) or video.stat().st_size <= 0:
        raise ComplianceChecklistError("approved export final.mp4 is missing or empty")
    receipt = _read_json(directory / "receipt.json", "receipt.json", export_root)
    if receipt.get("job_id") != job_id:
        raise ComplianceChecklistError("receipt.json does not match job")
    thumbnail = directory / "thumbnail.jpg"
    return directory.resolve(), approval, manifest, video.resolve(), thumbnail.resolve() if thumbnail.is_file() and is_within(thumbnail, export_root) else None


def _human_review_items(checked: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "id": item_id,
            "label": label,
            "checked": checked,
            "required": True,
        }
        for item_id, label in HUMAN_REVIEW_ITEMS
    ]


def _check(check_id: str, label: str, status: str, severity: str, evidence: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "severity": severity,
        "evidence": evidence,
    }


def _warning_messages(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"code": entry["code"], "message": entry["message"], "type": entry["type"]}
        for entry in entries
    ]


def _warning_checks(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        _check(
            entry["code"],
            entry["message"],
            "warn",
            "advisory",
            "deterministic local text scan",
        )
        for entry in entries
    ]


def _platform_copy_checks(
    export_root: Path,
    kit_root: Path,
    job_id: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    checks: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for platform in PLATFORM_ORDER:
        directory = kit_root / platform
        if not directory.is_dir() or not is_within(directory, export_root):
            raise ComplianceChecklistError(f"manual upload kit is missing platform: {platform}")
        metadata = _read_json(
            directory / "platform_metadata.json",
            f"{platform} platform_metadata.json",
            export_root,
        )
        if metadata.get("job_id") != job_id or metadata.get("platform") != platform:
            raise ComplianceChecklistError(f"{platform} metadata does not match job/platform")
        _require_safety(metadata, f"{platform} metadata")
        hashtags_text = _read_text(directory / "hashtags.txt", f"{platform} hashtags", export_root)
        hashtags = hashtag_tokens(hashtags_text)
        if platform == "youtube_shorts":
            title = _read_text(directory / "title.txt", "youtube_shorts title", export_root)
            description = _read_text(
                directory / "description.txt",
                "youtube_shorts description",
                export_root,
            )
            copy_value = title
            checks.append(
                _check(
                    "youtube_copy_exists",
                    "YouTube Shorts title exists",
                    "pass" if title else "fail",
                    "required",
                    str((directory / "title.txt").resolve()),
                )
            )
            warnings.extend(platform_copy_warnings(platform, title=title, description=description, hashtags=hashtags))
            warnings.extend(text_warning_checks("youtube_title", title))
            warnings.extend(text_warning_checks("youtube_description", description))
        else:
            caption = _read_text(directory / "caption.txt", f"{platform} caption", export_root)
            copy_value = caption
            checks.append(
                _check(
                    f"{platform}_copy_exists",
                    f"{platform.replace('_', ' ').title()} caption exists",
                    "pass" if caption else "fail",
                    "required",
                    str((directory / "caption.txt").resolve()),
                )
            )
            warnings.extend(platform_copy_warnings(platform, caption=caption, hashtags=hashtags))
            warnings.extend(text_warning_checks(f"{platform}_caption", caption))
        checks.append(
            _check(
                f"{platform}_hashtags_exist",
                f"{platform.replace('_', ' ').title()} hashtags exist",
                "pass" if hashtags else "warn",
                "advisory",
                str((directory / "hashtags.txt").resolve()),
            )
        )
        checks.append(
            _check(
                f"{platform}_copy_text_review",
                f"{platform.replace('_', ' ').title()} copy has no obvious unresolved placeholders",
                "pass" if copy_value else "fail",
                "required",
                str(directory.resolve()),
            )
        )
        warnings.extend(text_warning_checks(f"{platform}_hashtags", " ".join(hashtags)))
    return checks, warnings


def _preview_checks(export_root: Path, job_id: str, preview_manifest: dict[str, Any]) -> list[dict[str, str]]:
    platforms = preview_manifest.get("platforms", {})
    if not isinstance(platforms, dict):
        raise ComplianceChecklistError("preview manifest platforms are invalid")
    checks: list[dict[str, str]] = []
    for platform in PLATFORM_ORDER:
        details = platforms.get(platform)
        if not isinstance(details, dict):
            raise ComplianceChecklistError(f"preview manifest is missing platform: {platform}")
        for field in ("preview_html", "preview_text"):
            filename = str(details.get(field, ""))
            if not filename or Path(filename).name != filename:
                raise ComplianceChecklistError(f"{platform} preview manifest is missing {field}")
            path = compliance_directory(export_root, job_id).parent / "previews" / filename
            if not path.is_file() or not is_within(path, export_root):
                raise ComplianceChecklistError(f"{platform} preview file is missing: {filename}")
        checks.append(
            _check(
                f"{platform}_preview_exists",
                f"{platform.replace('_', ' ').title()} preview files exist",
                "pass",
                "required",
                str((compliance_directory(export_root, job_id).parent / "previews").resolve()),
            )
        )
    return checks


def _base_required_checks(
    export_dir: Path,
    approval: dict[str, Any],
    export_manifest: dict[str, Any],
    final_video: Path,
    kit_root: Path,
    upload_manifest: dict[str, Any],
    preview_root: Path,
) -> list[dict[str, str]]:
    _ = approval, export_manifest, upload_manifest
    return [
        _check("approved_export_exists", "Approved export bundle exists", "pass", "required", str(export_dir)),
        _check("approval_exists", "Approval record exists", "pass", "required", str((export_dir / "APPROVAL.json").resolve())),
        _check("export_manifest_exists", "Export manifest exists", "pass", "required", str((export_dir / "EXPORT_MANIFEST.json").resolve())),
        _check("final_video_exists", "Final video exists", "pass", "required", str(final_video)),
        _check("receipt_exists", "Receipt exists", "pass", "required", str((export_dir / "receipt.json").resolve())),
        _check("manual_upload_kit_exists", "Manual upload kit exists", "pass", "required", str(kit_root.resolve())),
        _check("upload_kit_manifest_exists", "Upload kit manifest exists", "pass", "required", str((kit_root / "UPLOAD_KIT_MANIFEST.json").resolve())),
        _check("preview_manifest_exists", "Preview cards exist", "pass", "required", str((preview_root / "PREVIEW_MANIFEST.json").resolve())),
        _check("safety_flags_preserved", "Safety flags preserved", "pass", "required", str((kit_root / "UPLOAD_KIT_MANIFEST.json").resolve())),
    ]


def _build_checklist(job_id: str, export_root: Path) -> dict[str, Any]:
    export_dir, approval, export_manifest, final_video, _ = _approved_export(export_root, job_id)
    try:
        upload_manifest = read_upload_kit_manifest(export_root, job_id)
        kit_root = kit_directory(export_root, job_id)
    except UploadKitManifestError as exc:
        raise ComplianceChecklistError(str(exc)) from exc
    if upload_manifest is None:
        raise ComplianceChecklistError(f"manual upload kit is missing for job {job_id}")
    _require_safety(upload_manifest, "upload kit manifest")
    if tuple(upload_manifest.get("platforms", ())) != PLATFORM_ORDER:
        raise ComplianceChecklistError("manual upload kit must contain all three supported platforms")
    try:
        preview_manifest = load_preview_manifest(export_root, job_id)
    except PreviewCardError as exc:
        raise ComplianceChecklistError(str(exc)) from exc
    if preview_manifest is None:
        raise ComplianceChecklistError(f"preview manifest is missing for job {job_id}")
    preview_root = compliance_directory(export_root, job_id).parent / "previews"
    safety = preview_manifest.get("safety")
    if not isinstance(safety, dict):
        raise ComplianceChecklistError("preview manifest safety block is missing")
    _require_safety(safety, "preview manifest safety")

    checks = _base_required_checks(
        export_dir,
        approval,
        export_manifest,
        final_video,
        kit_root,
        upload_manifest,
        preview_root,
    )
    checks.extend(_preview_checks(export_root, job_id, preview_manifest))
    copy_checks, warnings = _platform_copy_checks(export_root, kit_root, job_id)
    checks.extend(copy_checks)
    preview_warnings = preview_manifest.get("warnings", [])
    if not isinstance(preview_warnings, list):
        preview_warnings = []
    all_warnings = [
        entry
        for entry in [*warnings, *preview_warnings]
        if isinstance(entry, dict)
        and isinstance(entry.get("code"), str)
        and isinstance(entry.get("message"), str)
        and isinstance(entry.get("type"), str)
    ]
    checks.extend(_warning_checks(all_warnings))
    warning_entries = _warning_messages(all_warnings)

    existing = load_checklist(export_root, job_id)
    created_at = (
        str(existing.get("created_at"))
        if existing and existing.get("created_at")
        else _now()
    )
    return {
        "job_id": job_id,
        "created_at": created_at,
        "status": STATUS_NEEDS_REVIEW,
        "ready_for_manual_upload": False,
        "checks": checks,
        "human_review_items": _human_review_items(False),
        "safety": dict(SAFETY_FIELDS),
        "warnings": warning_entries,
        "errors": [],
        "source": {
            "export_dir": str(export_dir),
            "upload_kit_dir": str(kit_root.resolve()),
            "preview_manifest": str((preview_root / "PREVIEW_MANIFEST.json").resolve()),
        },
    }


def load_compliance_checklist(export_root: str | Path, job_id: str) -> dict[str, Any] | None:
    try:
        return load_checklist(export_root, job_id)
    except ComplianceStoreError as exc:
        raise ComplianceChecklistError(str(exc)) from exc


def generate_compliance_checklist(
    job_id: str,
    export_root: str | Path = "exports",
) -> ComplianceResult:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise ComplianceChecklistError("invalid job_id") from exc
    root = Path(export_root).expanduser().resolve()
    checklist = _build_checklist(safe_id, root)
    markdown = render_markdown(checklist)
    try:
        directory = write_checklist(root, safe_id, checklist, markdown)
    except ComplianceStoreError as exc:
        raise ComplianceChecklistError(str(exc)) from exc
    return ComplianceResult(safe_id, directory, checklist)


def mark_compliance_reviewed(
    job_id: str,
    export_root: str | Path = "exports",
    review_method: str = "local_cli",
) -> ComplianceResult:
    result = generate_compliance_checklist(job_id, export_root)
    if machine_status(result.checklist) == "fail":
        raise ComplianceChecklistError("required machine checks failed; cannot mark reviewed")
    checklist = dict(result.checklist)
    checklist["status"] = STATUS_READY
    checklist["ready_for_manual_upload"] = True
    checklist["reviewed_at"] = _now()
    checklist["review_method"] = review_method
    checklist["human_review_items"] = _human_review_items(True)
    markdown = render_markdown(checklist)
    try:
        directory = write_checklist(export_root, result.job_id, checklist, markdown)
    except ComplianceStoreError as exc:
        raise ComplianceChecklistError(str(exc)) from exc
    return ComplianceResult(result.job_id, directory, checklist)
