from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .job_index import is_within


APPROVAL_STATES = frozenset({"pending", "approved", "rejected", "needs_revision"})
SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_job_id(job_id: str) -> str:
    if not SAFE_JOB_ID.fullmatch(job_id) or job_id in {".", ".."}:
        raise ValueError("invalid job_id")
    return job_id


class ApprovalStore:
    def __init__(self, output_root: str | Path):
        self.output_root = Path(output_root).expanduser().resolve()
        self.approvals_root = self.output_root / "approvals"

    def _path(self, job_id: str) -> Path:
        safe_id = validate_job_id(job_id)
        path = self.approvals_root / f"{safe_id}.json"
        if not is_within(path, self.output_root):
            raise ValueError("approval path escapes output root")
        return path

    @staticmethod
    def pending(job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "state": "pending", "updated_at": None, "notes": ""}

    def read(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.is_file():
            return self.pending(job_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return self.pending(job_id)
        if not isinstance(value, dict) or value.get("state") not in APPROVAL_STATES:
            return self.pending(job_id)
        return {
            "job_id": job_id,
            "state": value["state"],
            "updated_at": value.get("updated_at"),
            "notes": str(value.get("notes", "")),
        }

    def write(self, job_id: str, state: str, notes: str = "") -> dict[str, Any]:
        path = self._path(job_id)
        if state not in APPROVAL_STATES:
            raise ValueError(f"invalid approval state: {state}")
        approval = {
            "job_id": job_id,
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "notes": str(notes),
        }
        self.approvals_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{job_id}.", suffix=".tmp", dir=self.approvals_root
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(approval, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return approval
