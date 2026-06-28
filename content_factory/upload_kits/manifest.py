from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within


MANIFEST_NAME = "UPLOAD_KIT_MANIFEST.json"
SAFETY_FIELDS = {
    "manual_upload_only": True,
    "publishing_status": "not_published",
    "live_publishing_enabled": False,
    "api_upload_attempted": False,
    "requires_human_upload": True,
}


class UploadKitManifestError(RuntimeError):
    pass


def kit_directory(export_root: str | Path, job_id: str) -> Path:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise UploadKitManifestError("invalid job_id") from exc
    root = Path(export_root).expanduser().resolve()
    path = root / "upload_kits" / safe_id
    if not is_within(path, root):
        raise UploadKitManifestError("upload kit path escapes export root")
    return path


def _safe(value: dict[str, Any]) -> bool:
    return all(value.get(key) == expected for key, expected in SAFETY_FIELDS.items())


def read_upload_kit_manifest(
    export_root: str | Path, job_id: str
) -> dict[str, Any] | None:
    kit_dir = kit_directory(export_root, job_id)
    path = kit_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    if not is_within(path, Path(export_root).expanduser().resolve()):
        raise UploadKitManifestError("upload kit manifest escapes export root")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UploadKitManifestError(f"upload kit manifest for {job_id} is invalid") from exc
    if not isinstance(value, dict) or value.get("job_id") != job_id or not _safe(value):
        raise UploadKitManifestError(f"upload kit manifest for {job_id} failed safety validation")
    return value


def write_upload_kit_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if not _safe(manifest):
        raise UploadKitManifestError("upload kit manifest failed safety validation")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".upload-kit.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
