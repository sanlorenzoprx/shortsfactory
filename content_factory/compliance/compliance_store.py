from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within
from content_factory.upload_kits.manifest import UploadKitManifestError, kit_directory

from .compliance_models import (
    JSON_NAME,
    MARKDOWN_NAME,
    SAFETY_FLAGS,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
)


class ComplianceStoreError(RuntimeError):
    """Safe refusal while reading or writing compliance checklist files."""


def compliance_directory(export_root: str | Path, job_id: str) -> Path:
    try:
        safe_id = validate_job_id(job_id)
        kit_root = kit_directory(export_root, safe_id)
    except (ValueError, UploadKitManifestError) as exc:
        raise ComplianceStoreError("invalid job_id") from exc
    root = Path(export_root).expanduser().resolve()
    path = kit_root / "compliance"
    if not is_within(path, root):
        raise ComplianceStoreError("compliance path escapes export root")
    return path


def _read_json(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_file() or not is_within(path, root):
        raise ComplianceStoreError("compliance checklist is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComplianceStoreError("compliance checklist is invalid") from exc
    if not isinstance(value, dict):
        raise ComplianceStoreError("compliance checklist must be a JSON object")
    return value


def _write_atomic(path: Path, value: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".compliance.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_checklist(value: dict[str, Any], job_id: str) -> dict[str, Any]:
    if value.get("job_id") != job_id:
        raise ComplianceStoreError("compliance checklist job_id does not match")
    if value.get("status") not in {STATUS_NEEDS_REVIEW, STATUS_READY}:
        raise ComplianceStoreError("compliance checklist status is invalid")
    safety = value.get("safety")
    if not isinstance(safety, dict):
        raise ComplianceStoreError("compliance safety block is missing")
    for key, expected in SAFETY_FLAGS.items():
        if safety.get(key) != expected:
            rendered = json.dumps(expected)
            raise ComplianceStoreError(
                f"compliance checklist must state {key}: {rendered}"
            )
    checks = value.get("checks")
    human_review_items = value.get("human_review_items")
    if not isinstance(checks, list) or not isinstance(human_review_items, list):
        raise ComplianceStoreError("compliance checklist entries are invalid")
    return value


def load_checklist(export_root: str | Path, job_id: str) -> dict[str, Any] | None:
    root = Path(export_root).expanduser().resolve()
    path = compliance_directory(root, job_id) / JSON_NAME
    if not path.is_file():
        return None
    value = _read_json(path, root)
    return validate_checklist(value, job_id)


def write_checklist(
    export_root: str | Path,
    job_id: str,
    checklist: dict[str, Any],
    markdown: str,
) -> Path:
    root = Path(export_root).expanduser().resolve()
    directory = compliance_directory(root, job_id)
    directory.mkdir(parents=True, exist_ok=True)
    validate_checklist(checklist, job_id)
    _write_atomic(
        directory / JSON_NAME,
        json.dumps(checklist, indent=2, ensure_ascii=False) + "\n",
    )
    _write_atomic(directory / MARKDOWN_NAME, markdown.rstrip() + "\n")
    return directory
