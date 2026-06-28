from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .revision_queue import utc_now_iso


MANIFEST_NAME = "REVISION_MANIFEST.json"


def build_revision_manifest(
    original_job_id: str,
    revised_job_id: str,
    revision_note: str,
    revision_task_path: Path,
    source_job_dir: Path,
    revised_job_dir: Path,
) -> dict[str, Any]:
    return {
        "original_job_id": original_job_id,
        "revised_job_id": revised_job_id,
        "created_at": utc_now_iso(),
        "revision_note": revision_note,
        "revision_task_path": str(revision_task_path),
        "source_job_dir": str(source_job_dir),
        "revised_job_dir": str(revised_job_dir),
        "revision_strategy": "deterministic_local_rules",
        "changed_files": [
            "script.txt",
            "captions.srt",
            "thumbnail.jpg",
            "short.mp4",
            "receipt.json",
        ],
        "requires_reapproval": True,
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
        "warnings": [],
    }


def write_revision_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def read_revision_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("requires_reapproval") is not True:
        return None
    if value.get("publishing_status") != "not_published":
        return None
    if value.get("live_publishing_enabled") is not False:
        return None
    return value
