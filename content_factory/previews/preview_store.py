from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within
from content_factory.upload_kits.manifest import UploadKitManifestError, kit_directory, read_upload_kit_manifest

from .platform_rules import platform_warnings
from .preview_models import PLATFORM_NAMES, PLATFORM_ORDER, PlatformPreview, PreviewResult, SAFETY_FLAGS
from .preview_renderer import render_html, render_text


MANIFEST_NAME = "PREVIEW_MANIFEST.json"
REQUIRED_PLATFORM_FILES = {
    "youtube_shorts": ("platform_metadata.json", "upload_checklist.md", "title.txt", "description.txt", "hashtags.txt"),
    "tiktok": ("platform_metadata.json", "upload_checklist.md", "caption.txt", "hashtags.txt"),
    "instagram_reels": ("platform_metadata.json", "upload_checklist.md", "caption.txt", "hashtags.txt"),
}


class PreviewCardError(RuntimeError):
    """Safe refusal while generating local preview cards."""


def _read_json(path: Path, label: str, root: Path) -> dict[str, Any]:
    if not path.is_file() or not is_within(path, root):
        raise PreviewCardError(f"{label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreviewCardError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise PreviewCardError(f"{label} must be a JSON object")
    return value


def _read_text(path: Path, label: str, root: Path) -> str:
    if not path.is_file() or not is_within(path, root):
        raise PreviewCardError(f"{label} is missing")
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise PreviewCardError(f"{label} is unreadable") from exc


def _require_safety(value: dict[str, Any], label: str) -> None:
    for key, expected in SAFETY_FLAGS.items():
        if value.get(key) != expected:
            rendered = json.dumps(expected)
            raise PreviewCardError(f"{label} must state {key}: {rendered}")


def _approved_export(export_root: Path, job_id: str) -> tuple[Path, Path, Path | None, dict[str, Any]]:
    directory = export_root / "approved" / job_id
    if not directory.is_dir() or not is_within(directory, export_root):
        raise PreviewCardError(f"approved export bundle is missing for job {job_id}")
    approval = _read_json(directory / "APPROVAL.json", "APPROVAL.json", export_root)
    if approval.get("job_id") != job_id or approval.get("state") != "approved":
        raise PreviewCardError(f"export bundle is not approved for job {job_id}")
    manifest = _read_json(directory / "EXPORT_MANIFEST.json", "EXPORT_MANIFEST.json", export_root)
    if manifest.get("job_id") != job_id:
        raise PreviewCardError("export manifest does not match job")
    if manifest.get("publishing_status") != "not_published" or manifest.get("live_publishing_enabled") is not False:
        raise PreviewCardError("export manifest must remain not_published with live publishing disabled")
    video = directory / "final.mp4"
    if not video.is_file() or not is_within(video, export_root) or video.stat().st_size <= 0:
        raise PreviewCardError("approved export final.mp4 is missing or empty")
    thumbnail = directory / "thumbnail.jpg"
    return directory.resolve(), video.resolve(), thumbnail.resolve() if thumbnail.is_file() and is_within(thumbnail, export_root) else None, manifest


def _hashtags(value: str) -> tuple[str, ...]:
    return tuple(token for token in value.replace("\n", " ").split() if token)


def _platform_preview(
    platform: str,
    kit_root: Path,
    export_root: Path,
    job_id: str,
    video: Path,
    thumbnail: Path | None,
) -> PlatformPreview:
    directory = kit_root / platform
    if not directory.is_dir() or not is_within(directory, export_root):
        raise PreviewCardError(f"manual upload kit is missing platform: {platform}")
    for filename in REQUIRED_PLATFORM_FILES[platform]:
        path = directory / filename
        if not path.is_file() or not is_within(path, export_root):
            raise PreviewCardError(f"{platform} upload kit is missing {filename}")
    metadata = _read_json(directory / "platform_metadata.json", f"{platform} platform_metadata.json", export_root)
    if metadata.get("job_id") != job_id or metadata.get("platform") != platform:
        raise PreviewCardError(f"{platform} metadata does not match job/platform")
    _require_safety(metadata, f"{platform} metadata")
    checklist = _read_text(directory / "upload_checklist.md", f"{platform} checklist", export_root)
    hashtags = _hashtags(_read_text(directory / "hashtags.txt", f"{platform} hashtags", export_root))
    title = _read_text(directory / "title.txt", "youtube_shorts title", export_root) if platform == "youtube_shorts" else ""
    description = _read_text(directory / "description.txt", "youtube_shorts description", export_root) if platform == "youtube_shorts" else ""
    caption = _read_text(directory / "caption.txt", f"{platform} caption", export_root) if platform != "youtube_shorts" else str(metadata.get("caption", ""))
    warnings = platform_warnings(
        platform,
        title=title,
        caption=caption,
        description=description,
        hashtags=hashtags,
        final_video_present=video.is_file(),
        manual_upload_only=metadata.get("manual_upload_only") is True,
    )
    return PlatformPreview(platform, PLATFORM_NAMES[platform], video, thumbnail, title, caption, description, hashtags, checklist, metadata, warnings)


def preview_directory(export_root: str | Path, job_id: str) -> Path:
    try:
        safe_id = validate_job_id(job_id)
        kit_root = kit_directory(export_root, safe_id)
    except (ValueError, UploadKitManifestError) as exc:
        raise PreviewCardError("invalid job_id") from exc
    path = kit_root / "previews"
    root = Path(export_root).expanduser().resolve()
    if not is_within(path, root):
        raise PreviewCardError("preview path escapes export root")
    return path


def load_preview_manifest(export_root: str | Path, job_id: str) -> dict[str, Any] | None:
    root = Path(export_root).expanduser().resolve()
    path = preview_directory(root, job_id) / MANIFEST_NAME
    if not path.is_file():
        return None
    value = _read_json(path, MANIFEST_NAME, root)
    if value.get("job_id") != job_id or value.get("status") != "ready_for_manual_review":
        raise PreviewCardError("preview manifest does not match job or status")
    safety = value.get("safety")
    if not isinstance(safety, dict):
        raise PreviewCardError("preview manifest safety block is missing")
    _require_safety(safety, "preview manifest safety")
    return value


def generate_preview_cards(job_id: str, export_root: str | Path = "exports") -> PreviewResult:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise PreviewCardError("invalid job_id") from exc
    root = Path(export_root).expanduser().resolve()
    try:
        upload_manifest = read_upload_kit_manifest(root, safe_id)
        kit_root = kit_directory(root, safe_id)
    except UploadKitManifestError as exc:
        raise PreviewCardError(str(exc)) from exc
    if upload_manifest is None:
        raise PreviewCardError(f"manual upload kit is missing for job {safe_id}")
    _require_safety(upload_manifest, "upload kit manifest")
    if tuple(upload_manifest.get("platforms", ())) != PLATFORM_ORDER:
        raise PreviewCardError("manual upload kit must contain all three supported platforms")
    export_dir, video, thumbnail, _ = _approved_export(root, safe_id)
    previews = {
        platform: _platform_preview(platform, kit_root, root, safe_id, video, thumbnail)
        for platform in PLATFORM_ORDER
    }
    destination = preview_directory(root, safe_id)
    kit_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".previews.", dir=kit_root))
    try:
        platform_manifest: dict[str, Any] = {}
        all_warnings: list[dict[str, str]] = []
        for platform, preview in previews.items():
            html_name = f"{platform}_preview.html"
            text_name = f"{platform}_preview.txt"
            (temporary / html_name).write_text(render_html(preview), encoding="utf-8")
            (temporary / text_name).write_text(render_text(preview).rstrip() + "\n", encoding="utf-8")
            warnings = list(preview.warnings)
            all_warnings.extend(warnings)
            platform_manifest[platform] = {
                "preview_html": html_name,
                "preview_text": text_name,
                "status": "ready",
                "warnings": warnings,
            }
        existing = load_preview_manifest(root, safe_id)
        created_at = str(existing.get("created_at")) if existing and existing.get("created_at") else datetime.now(timezone.utc).isoformat()
        manifest = {
            "job_id": safe_id,
            "created_at": created_at,
            "status": "ready_for_manual_review",
            "source": {
                "upload_kit_manifest": str((kit_root / "UPLOAD_KIT_MANIFEST.json").resolve()),
                "export_manifest": str((export_dir / "EXPORT_MANIFEST.json").resolve()),
            },
            "platforms": platform_manifest,
            "safety": dict(SAFETY_FLAGS),
            "warnings": all_warnings,
        }
        (temporary / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir() or not is_within(destination, root):
                raise PreviewCardError("existing preview path is not a safe directory")
            shutil.rmtree(destination)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return PreviewResult(safe_id, destination, manifest)
