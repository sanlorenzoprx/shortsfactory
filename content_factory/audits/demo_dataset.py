from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from content_factory.mission_control.job_index import JobRecord, is_within


MEDIA_SUFFIXES = frozenset({".mp4", ".wav", ".webm", ".jpg", ".jpeg", ".png"})


class DemoDatasetError(RuntimeError):
    """Raised when audit evidence cannot be packaged safely."""


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")
    return path


def _copy_checked(source: Path, destination: Path, source_root: Path) -> None:
    if not source.is_file() or not is_within(source, source_root):
        raise DemoDatasetError(f"audit source is outside configured root: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _media_manifest(source_dir: Path, source_root: Path, destination: Path, copy_media: bool) -> dict[str, Any]:
    detected = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file() or path.suffix.casefold() not in MEDIA_SUFFIXES:
            continue
        if not is_within(path, source_root):
            raise DemoDatasetError("media path escapes configured root")
        copied = False
        if copy_media:
            _copy_checked(path, destination / path.name, source_root)
            copied = True
        detected.append({"name": path.name, "path": str(path.resolve()), "size_bytes": path.stat().st_size, "copied": copied})
    return {"media_files_detected": detected, "copy_media_enabled": copy_media}


def _job_evidence(job: JobRecord, destination: Path, output_root: Path, copy_media: bool) -> None:
    for name in ("receipt.json", "script.txt", "captions.srt", "REVISION_MANIFEST.json"):
        source = job.artifacts.get(name)
        if source is not None:
            _copy_checked(source, destination / name, output_root)
    write_json(destination / "media_manifest.json", _media_manifest(job.job_dir, output_root, destination, copy_media))


def _export_evidence(export_dir: Path, destination: Path, export_root: Path, copy_media: bool) -> None:
    files = []
    for source in sorted(export_dir.iterdir()):
        if not source.is_file() or not is_within(source, export_root):
            continue
        is_media = source.suffix.casefold() in MEDIA_SUFFIXES
        copied = not is_media or copy_media
        if copied:
            _copy_checked(source, destination / source.name, export_root)
        files.append({"name": source.name, "size_bytes": source.stat().st_size, "media": is_media, "copied": copied})
    write_json(destination / "export_file_manifest.json", {"files": files, "copy_media_enabled": copy_media})


def _upload_kit_evidence(upload_kit_dir: Path, destination: Path, export_root: Path, copy_media: bool) -> None:
    manifest = upload_kit_dir / "UPLOAD_KIT_MANIFEST.json"
    _copy_checked(manifest, destination / manifest.name, export_root)
    for platform_dir in sorted(path for path in upload_kit_dir.iterdir() if path.is_dir()):
        platform_destination = destination / platform_dir.name
        for source in sorted(platform_dir.iterdir()):
            if not source.is_file() or not is_within(source, export_root):
                continue
            is_media = source.suffix.casefold() in MEDIA_SUFFIXES
            if not is_media or copy_media:
                _copy_checked(source, platform_destination / source.name, export_root)


def create_demo_dataset(
    staging_root: Path,
    *,
    original_job: JobRecord,
    revised_job: JobRecord,
    original_quality: dict[str, Any],
    revised_quality: dict[str, Any],
    export_dir: Path,
    upload_kit_dir: Path,
    template_validation: dict[str, Any],
    template_preview: str,
    template_manifest: dict[str, Any],
    output_root: Path,
    export_root: Path,
    copy_media: bool,
) -> None:
    staging_root.mkdir(parents=True, exist_ok=True)
    _job_evidence(original_job, staging_root / "demo_jobs" / "original", output_root, copy_media)
    _job_evidence(revised_job, staging_root / "demo_jobs" / "revised", output_root, copy_media)
    write_json(staging_root / "demo_quality" / "original_quality.json", original_quality)
    write_json(staging_root / "demo_quality" / "revised_quality.json", revised_quality)
    _export_evidence(export_dir, staging_root / "demo_exports" / "approved", export_root, copy_media)
    _upload_kit_evidence(upload_kit_dir, staging_root / "demo_upload_kits", export_root, copy_media)
    write_json(staging_root / "demo_templates" / "template_validation.json", template_validation)
    write_text(staging_root / "demo_templates" / "script_default_preview.txt", template_preview)
    write_json(staging_root / "demo_templates" / "template_manifest.json", template_manifest)
    write_text(
        staging_root / "README.md",
        """# Phase 3 Demo Dataset

This local proof package demonstrates:

Generate -> Score -> Review -> Revise -> Re-score -> Approve -> Export -> Manual Upload Kit -> Template Control

Media is represented by manifests by default. Re-run `phase3_audit.py` with
`--copy-media` only when local media copies are intentionally required.

This dataset is manual-upload-only and contains no publishing capability.
""",
    )
