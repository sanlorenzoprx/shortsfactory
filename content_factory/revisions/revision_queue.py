from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import find_job, is_within


REVISION_STATES = frozenset(
    {"needs_revision", "revision_queued", "revision_complete", "revision_failed"}
)


class RevisionTaskError(RuntimeError):
    """A safe, user-facing revision task error."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevisionQueue:
    def __init__(self, output_root: str | Path = "output"):
        self.output_root = Path(output_root).expanduser().resolve()
        self.revisions_root = self.output_root / "revisions"

    def task_path(self, job_id: str) -> Path:
        try:
            safe_id = validate_job_id(job_id)
        except ValueError as exc:
            raise RevisionTaskError("invalid job_id") from exc
        path = self.revisions_root / f"{safe_id}.json"
        if not is_within(path, self.output_root):
            raise RevisionTaskError("revision task path escapes output root")
        return path

    def read(self, job_id: str) -> dict[str, Any] | None:
        path = self.task_path(job_id)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RevisionTaskError(f"revision task for {job_id} is invalid") from exc
        if not isinstance(value, dict) or value.get("job_id") != job_id:
            raise RevisionTaskError(f"revision task for {job_id} does not match job")
        if value.get("state") not in REVISION_STATES:
            raise RevisionTaskError(f"revision task for {job_id} has an invalid state")
        return value

    def create(self, job_id: str, revision_note: str) -> dict[str, Any]:
        job = find_job(self.output_root, job_id)
        if job is None:
            raise RevisionTaskError(f"job not found: {job_id}")
        note = str(revision_note).strip()
        if not note:
            raise RevisionTaskError("revision note is required")
        existing = self.read(job_id)
        now = utc_now_iso()
        task = {
            "job_id": job_id,
            "state": "revision_queued",
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
            "revision_note": note,
            "requested_by": "local_user",
            "source_receipt": str(job.artifacts["receipt.json"]),
            "revised_job_id": None,
            "attempts": int(existing.get("attempts", 0)) if existing else 0,
            "warnings": [],
        }
        return self.write(task)

    def write(self, task: dict[str, Any]) -> dict[str, Any]:
        job_id = str(task.get("job_id", ""))
        path = self.task_path(job_id)
        state = task.get("state")
        if state not in REVISION_STATES:
            raise RevisionTaskError(f"invalid revision state: {state}")
        task = dict(task)
        task["updated_at"] = utc_now_iso()
        self.revisions_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{job_id}.", suffix=".tmp", dir=self.revisions_root
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(task, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return task

    def complete(self, task: dict[str, Any], revised_job_id: str) -> dict[str, Any]:
        updated = dict(task)
        updated["state"] = "revision_complete"
        updated["revised_job_id"] = validate_job_id(revised_job_id)
        updated["attempts"] = int(task.get("attempts", 0)) + 1
        return self.write(updated)

    def fail(self, task: dict[str, Any], warning: str) -> dict[str, Any]:
        updated = dict(task)
        updated["state"] = "revision_failed"
        updated["attempts"] = int(task.get("attempts", 0)) + 1
        updated["warnings"] = [*list(task.get("warnings", [])), str(warning)]
        return self.write(updated)
