from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within

from .checklist_builder import build_checklist
from .manifest import (
    MANIFEST_NAME,
    SAFETY_FIELDS,
    UploadKitManifestError,
    kit_directory,
    read_upload_kit_manifest,
    write_upload_kit_manifest,
)
from .metadata_formatter import format_platform_copy
from .platform_profiles import PLATFORM_ORDER, PlatformProfile, selected_platforms


class UploadKitError(RuntimeError):
    """A safe, user-facing refusal to create a manual upload kit."""


@dataclass(frozen=True)
class UploadKitSource:
    job_id: str
    export_dir: Path
    export_manifest: dict[str, Any]
    approval: dict[str, Any]
    receipt: dict[str, Any]
    script: str
    publisher_package: dict[str, Any]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class UploadKitResult:
    job_id: str
    upload_kit_dir: Path
    manifest: dict[str, Any]


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UploadKitError(f"{label} is missing or invalid") from exc
    if not isinstance(value, dict):
        raise UploadKitError(f"{label} must be a JSON object")
    return value


def _source(export_root: Path, job_id: str) -> UploadKitSource:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise UploadKitError("invalid job_id") from exc
    approved_root = export_root / "approved"
    source_dir = approved_root / safe_id
    if not source_dir.is_dir() or not is_within(source_dir, approved_root):
        raise UploadKitError(f"approved export bundle is missing for job {safe_id}")
    required = {
        "EXPORT_MANIFEST.json": source_dir / "EXPORT_MANIFEST.json",
        "APPROVAL.json": source_dir / "APPROVAL.json",
        "receipt.json": source_dir / "receipt.json",
        "final.mp4": source_dir / "final.mp4",
    }
    for name, path in required.items():
        if not path.is_file() or not is_within(path, approved_root):
            raise UploadKitError(f"approved export bundle is missing {name}")
    approval = _read_json(required["APPROVAL.json"], "APPROVAL.json")
    if approval.get("job_id") != safe_id or approval.get("state") != "approved":
        raise UploadKitError(f"export approval is not approved for job {safe_id}")
    export_manifest = _read_json(required["EXPORT_MANIFEST.json"], "EXPORT_MANIFEST.json")
    if export_manifest.get("job_id") != safe_id:
        raise UploadKitError("export manifest does not match job")
    if export_manifest.get("publishing_status") != "not_published":
        raise UploadKitError("export manifest must state publishing_status: not_published")
    if export_manifest.get("live_publishing_enabled") is not False:
        raise UploadKitError("export manifest must state live_publishing_enabled: false")
    if required["final.mp4"].stat().st_size <= 0:
        raise UploadKitError("approved final.mp4 is empty")
    receipt = _read_json(required["receipt.json"], "receipt.json")
    if receipt.get("job_id") != safe_id:
        raise UploadKitError("receipt.json does not match job")
    script_path = source_dir / "script.txt"
    try:
        script = script_path.read_text(encoding="utf-8") if script_path.is_file() else ""
    except (OSError, UnicodeError):
        script = ""
    warnings: list[str] = []
    publisher_path = source_dir / "publisher_package.json"
    publisher_package: dict[str, Any] = {}
    if publisher_path.is_file():
        try:
            publisher_package = _read_json(publisher_path, "publisher_package.json")
        except UploadKitError:
            warnings.append("publisher_package.json was invalid; receipt/script fallback used")
    return UploadKitSource(
        job_id=safe_id,
        export_dir=source_dir.resolve(),
        export_manifest=export_manifest,
        approval=approval,
        receipt=receipt,
        script=script,
        publisher_package=publisher_package,
        warnings=tuple(warnings),
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _replace_directory(temporary: Path, destination: Path, export_root: Path) -> None:
    if destination.exists() or destination.is_symlink():
        if not is_within(destination, export_root) or destination.is_symlink() or not destination.is_dir():
            raise UploadKitError("existing platform kit path is not a safe directory")
        shutil.rmtree(destination)
    temporary.replace(destination)


def _build_platform(
    source: UploadKitSource,
    profile: PlatformProfile,
    kit_root: Path,
    export_root: Path,
    created_at: str,
) -> dict[str, Any]:
    destination = kit_root / profile.key
    if not is_within(destination, export_root):
        raise UploadKitError("platform kit path escapes export root")
    temporary = Path(tempfile.mkdtemp(prefix=f".{profile.key}.", dir=kit_root))
    try:
        files: list[str] = ["final.mp4"]
        shutil.copy2(source.export_dir / "final.mp4", temporary / "final.mp4")
        missing_optional: list[str] = []
        for optional in ("thumbnail.jpg", "captions.srt"):
            source_path = source.export_dir / optional
            if source_path.is_file() and is_within(source_path, source.export_dir):
                shutil.copy2(source_path, temporary / optional)
                files.append(optional)
            else:
                missing_optional.append(optional)

        copy = format_platform_copy(
            profile, source.receipt, source.script, source.publisher_package
        )
        if profile.has_title:
            _write_text(temporary / "title.txt", copy["title"])
            files.append("title.txt")
        if profile.has_description:
            _write_text(temporary / "description.txt", copy["description"])
            files.append("description.txt")
        if not profile.has_title:
            _write_text(temporary / "caption.txt", copy["caption"])
            files.append("caption.txt")
        _write_text(temporary / "hashtags.txt", "\n".join(copy["hashtags"]))
        files.append("hashtags.txt")
        _write_text(temporary / "upload_checklist.md", build_checklist(profile.key))
        files.append("upload_checklist.md")
        files.append("platform_metadata.json")
        metadata = {
            "job_id": source.job_id,
            "platform": profile.key,
            "created_at": created_at,
            "source_export_dir": str(source.export_dir),
            "platform_dir": str(destination.resolve()),
            "files": files,
            "missing_optional_files": missing_optional,
            "title": copy["title"],
            "caption": copy["caption"],
            "description": copy["description"],
            "hashtags": copy["hashtags"],
            **SAFETY_FIELDS,
            "warnings": list(source.warnings),
        }
        _write_json(temporary / "platform_metadata.json", metadata)
        _replace_directory(temporary, destination, export_root)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return metadata


def _read_platform_metadata(
    kit_root: Path, platform: str, job_id: str, export_root: Path
) -> dict[str, Any] | None:
    path = kit_root / platform / "platform_metadata.json"
    if not path.is_file() or not is_within(path, export_root):
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("job_id") != job_id or value.get("platform") != platform:
        return None
    if any(value.get(key) != expected for key, expected in SAFETY_FIELDS.items()):
        return None
    return value


def build_upload_kit(
    job_id: str,
    export_root: str | Path = "exports",
    platform: str = "all",
) -> UploadKitResult:
    root = Path(export_root).expanduser().resolve()
    source = _source(root, job_id)
    try:
        profiles = selected_platforms(platform)
        existing = read_upload_kit_manifest(root, source.job_id)
        kit_root = kit_directory(root, source.job_id)
    except (ValueError, UploadKitManifestError) as exc:
        raise UploadKitError(str(exc)) from exc
    kit_root.mkdir(parents=True, exist_ok=True)
    created_at = (
        str(existing.get("created_at"))
        if existing and existing.get("created_at")
        else datetime.now(timezone.utc).isoformat()
    )
    for profile in profiles:
        _build_platform(source, profile, kit_root, root, created_at)

    platform_metadata = {
        key: metadata
        for key in PLATFORM_ORDER
        if (metadata := _read_platform_metadata(kit_root, key, source.job_id, root))
        is not None
    }
    platforms = list(platform_metadata)
    manifest = {
        "job_id": source.job_id,
        "created_at": created_at,
        "source_export_dir": str(source.export_dir),
        "upload_kit_dir": str(kit_root.resolve()),
        "platforms": platforms,
        "platform_dirs": {
            key: str((kit_root / key).resolve()) for key in platforms
        },
        "included_files": {
            key: list(platform_metadata[key].get("files", [])) for key in platforms
        },
        "missing_optional_files": {
            key: list(platform_metadata[key].get("missing_optional_files", []))
            for key in platforms
        },
        **SAFETY_FIELDS,
        "warnings": list(source.warnings),
    }
    write_upload_kit_manifest(kit_root / MANIFEST_NAME, manifest)
    return UploadKitResult(source.job_id, kit_root, manifest)


def load_upload_kit_preview(
    export_root: str | Path, job_id: str
) -> dict[str, Any] | None:
    root = Path(export_root).expanduser().resolve()
    try:
        manifest = read_upload_kit_manifest(root, job_id)
        kit_root = kit_directory(root, job_id)
    except UploadKitManifestError as exc:
        raise UploadKitError(str(exc)) from exc
    if manifest is None:
        return None
    previews: dict[str, Any] = {}
    for platform in manifest.get("platforms", []):
        if platform not in PLATFORM_ORDER:
            continue
        metadata = _read_platform_metadata(kit_root, platform, job_id, root)
        checklist_path = kit_root / platform / "upload_checklist.md"
        if metadata is None or not checklist_path.is_file() or not is_within(checklist_path, root):
            continue
        try:
            checklist = checklist_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            checklist = "Checklist unavailable."
        previews[platform] = {"metadata": metadata, "checklist": checklist}
    return {"manifest": manifest, "platforms": previews}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create local platform-specific manual upload kits from an approved export."
    )
    parser.add_argument("--job-id", required=True, help="Approved exported job ID")
    parser.add_argument("--export-root", default="exports", help="Local export root")
    parser.add_argument(
        "--platform",
        default="all",
        help="youtube_shorts, tiktok, instagram_reels, or all",
    )
    parser.add_argument("--json", action="store_true", help="Print the upload kit manifest JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_upload_kit(args.job_id, args.export_root, args.platform)
    except (UploadKitError, OSError) as exc:
        print(f"Upload kit refused: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.manifest, indent=2, ensure_ascii=False))
    else:
        print(f"Manual upload kit created: {result.upload_kit_dir}")
        print(f"Platforms: {', '.join(result.manifest['platforms'])}")
        print("Status: MANUAL UPLOAD ONLY - NOT PUBLISHED")
    return 0
