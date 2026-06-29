from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from content_factory.mission_control.job_index import is_within


ARTIFACTS = {
    "plan": "batch_plan.json",
    "trends": "trends.json",
    "ideas": "ideas.json",
    "verdicts": "lit_verdicts.json",
    "decisions": "verdict_decisions.json",
    "jobs": "generated_jobs.json",
    "quality": "quality_gates.json",
    "compliance": "compliance_gates.json",
    "publish_queue": "publish_queue.json",
    "publish": "publish_attempts.json",
    "analytics": "analytics_snapshots.json",
    "performance": "performance_review.json",
    "next_plan": "next_batch_plan.json",
    "receipt": "AUTOPILOT_RECEIPT.json",
}


class AutopilotStoreError(RuntimeError):
    pass


class AutopilotStore:
    def __init__(self, output_root: str | Path = "output"):
        self.output_root = Path(output_root).expanduser().resolve()
        self.batches_root = self.output_root / "autopilot" / "batches"

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def new_batch_id(self) -> str:
        return f"ap_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}_{uuid4().hex[:6]}"

    def batch_dir(self, batch_id: str) -> Path:
        if not batch_id or Path(batch_id).name != batch_id or not batch_id.startswith("ap_"):
            raise AutopilotStoreError("invalid batch_id")
        path = self.batches_root / batch_id
        if not is_within(path, self.batches_root):
            raise AutopilotStoreError("batch path escapes autopilot root")
        return path

    def path(self, batch_id: str, artifact: str) -> Path:
        if artifact not in ARTIFACTS:
            raise AutopilotStoreError(f"unknown artifact: {artifact}")
        return self.batch_dir(batch_id) / ARTIFACTS[artifact]

    def exists(self, batch_id: str, artifact: str) -> bool:
        return self.path(batch_id, artifact).is_file()

    def write(self, batch_id: str, artifact: str, value: Any) -> Path:
        path = self.path(batch_id, artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".autopilot.", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def read(self, batch_id: str, artifact: str) -> Any:
        path = self.path(batch_id, artifact)
        if not path.is_file():
            raise AutopilotStoreError(f"artifact is missing: {path.name}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AutopilotStoreError(f"artifact is invalid: {path.name}") from exc

    def list_batches(self) -> list[dict[str, Any]]:
        if not self.batches_root.is_dir():
            return []
        rows = []
        for directory in sorted(self.batches_root.iterdir(), reverse=True):
            if not directory.is_dir() or not directory.name.startswith("ap_"):
                continue
            try:
                source = self.read(directory.name, "receipt") if self.exists(directory.name, "receipt") else self.read(directory.name, "plan")
            except AutopilotStoreError:
                continue
            rows.append({
                "batch_id": directory.name,
                "mode": source.get("mode", source.get("config", {}).get("mode", "unknown")),
                "status": source.get("status", "running"),
                "created_at": source.get("created_at", ""),
            })
        return rows
