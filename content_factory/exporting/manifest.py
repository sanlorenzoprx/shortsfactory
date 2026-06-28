from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import JobRecord, is_within


MANIFEST_NAME = "EXPORT_MANIFEST.json"


def build_export_manifest(
    job: JobRecord,
    export_dir: Path,
    included_files: Iterable[str],
    missing_optional_files: Iterable[str],
) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "created_at": job.created_at,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "approval_state": "approved",
        "source_job_dir": str(job.job_dir),
        "export_dir": str(export_dir.resolve()),
        "final_video": "final.mp4",
        "included_files": list(included_files),
        "missing_optional_files": list(missing_optional_files),
        "warnings": list(job.warnings),
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
    }


def write_export_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def export_directory(export_root: str | Path, job_id: str) -> Path:
    safe_id = validate_job_id(job_id)
    root = Path(export_root).expanduser().resolve()
    path = root / "approved" / safe_id
    if not is_within(path, root):
        raise ValueError("export path escapes export root")
    return path


def read_export_manifest(export_root: str | Path, job_id: str) -> dict[str, Any] | None:
    export_dir = export_directory(export_root, job_id)
    path = export_dir / MANIFEST_NAME
    if not path.is_file() or not is_within(path, Path(export_root).expanduser().resolve()):
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("job_id") != job_id:
        return None
    if value.get("publishing_status") != "not_published":
        return None
    if value.get("live_publishing_enabled") is not False:
        return None
    return value
