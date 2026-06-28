from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within

from .quality_model import report_is_safe


class QualityStoreError(RuntimeError):
    """A safe, user-facing quality report storage error."""


class QualityStore:
    def __init__(self, output_root: str | Path = "output"):
        self.output_root = Path(output_root).expanduser().resolve()
        self.quality_root = self.output_root / "quality"

    def report_path(self, job_id: str) -> Path:
        try:
            safe_id = validate_job_id(job_id)
        except ValueError as exc:
            raise QualityStoreError("invalid job_id") from exc
        path = self.quality_root / f"{safe_id}.json"
        if not is_within(path, self.output_root):
            raise QualityStoreError("quality report path escapes output root")
        return path

    def read(self, job_id: str) -> dict[str, Any] | None:
        path = self.report_path(job_id)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise QualityStoreError(f"quality report for {job_id} is invalid") from exc
        if not isinstance(value, dict) or value.get("job_id") != job_id:
            raise QualityStoreError(f"quality report for {job_id} does not match job")
        if not report_is_safe(value):
            raise QualityStoreError(f"quality report for {job_id} failed safety validation")
        return value

    def write(self, report: dict[str, Any]) -> Path:
        job_id = str(report.get("job_id", ""))
        path = self.report_path(job_id)
        if not report_is_safe(report):
            raise QualityStoreError("quality report failed safety validation")
        self.quality_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{job_id}.", suffix=".tmp", dir=self.quality_root
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(report, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return path
