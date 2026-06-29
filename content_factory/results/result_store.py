from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import is_within

from .result_models import LEDGER_FILENAME, METRIC_FIELDS, SAFETY_FLAGS, SUMMARY_FILENAME
from .result_report import render_results_summary
from .result_validator import (
    ResultsValidationError,
    validate_metrics,
    validate_platform,
    validate_ready_job,
    validate_url,
)


@dataclass(frozen=True)
class ResultsLedgerResult:
    entry: dict[str, Any]
    ledger: dict[str, Any]
    summary_path: Path


class ResultsLedgerError(RuntimeError):
    """Safe refusal while reading or writing local results ledger data."""


class ResultsLedgerStore:
    def __init__(
        self,
        ledger_root: str | Path = "results_ledger",
        *,
        export_root: str | Path = "exports",
        output_root: str | Path = "output",
    ):
        self.ledger_root = Path(ledger_root).expanduser().resolve()
        self.export_root = Path(export_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self.entries_root = self.ledger_root / "entries"
        self.reports_root = self.ledger_root / "reports"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _entry_path(self, entry_id: str) -> Path:
        filename = f"{entry_id}.json"
        path = self.entries_root / filename
        if Path(filename).name != filename or not is_within(path, self.ledger_root):
            raise ResultsLedgerError("invalid entry_id")
        return path

    def _atomic_write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".results.",
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

    def _read_json(self, path: Path, label: str) -> dict[str, Any]:
        if not path.is_file() or not is_within(path, self.ledger_root):
            raise ResultsLedgerError(f"{label} is missing")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResultsLedgerError(f"{label} is invalid") from exc
        if not isinstance(value, dict):
            raise ResultsLedgerError(f"{label} must be a JSON object")
        return value

    def _entry_id(self, job_id: str, platform: str) -> str:
        return f"result-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}-{job_id}-{platform}"

    def _validate_entry_shape(self, entry: dict[str, Any]) -> dict[str, Any]:
        job_id = str(entry.get("job_id", ""))
        try:
            validate_job_id(job_id)
        except ValueError as exc:
            raise ResultsLedgerError("entry job_id is invalid") from exc
        validate_platform(str(entry.get("platform", "")))
        validate_url(str(entry.get("manual_upload_url", "")))
        entry["metrics"] = validate_metrics(entry.get("metrics", {}))
        safety = entry.get("safety")
        if not isinstance(safety, dict):
            raise ResultsLedgerError("entry safety block is missing")
        for key, expected in SAFETY_FLAGS.items():
            if safety.get(key) != expected:
                rendered = json.dumps(expected)
                raise ResultsLedgerError(f"entry must state {key}: {rendered}")
        context = entry.get("context")
        if not isinstance(context, dict):
            raise ResultsLedgerError("entry context is invalid")
        return entry

    def _ledger_path(self) -> Path:
        path = self.ledger_root / LEDGER_FILENAME
        if not is_within(path, self.ledger_root):
            raise ResultsLedgerError("ledger path escapes ledger root")
        return path

    def _summary_path(self) -> Path:
        path = self.reports_root / SUMMARY_FILENAME
        if not is_within(path, self.ledger_root):
            raise ResultsLedgerError("summary path escapes ledger root")
        return path

    def _build_context(self, validation: dict[str, Any]) -> dict[str, Any]:
        quality = validation.get("quality")
        quality_score = quality.get("overall_score") if isinstance(quality, dict) else None
        quality_status = quality.get("status") if isinstance(quality, dict) else None
        return {
            "quality_score": quality_score,
            "quality_status": quality_status,
            "compliance_status": validation["compliance"].get("status"),
            "template_ids": validation.get("template_ids", {}),
            "template_hashes": validation.get("template_hashes", {}),
        }

    def _write_summary(self, entries: list[dict[str, Any]]) -> Path:
        path = self._summary_path()
        self._atomic_write(path, render_results_summary(entries).rstrip() + "\n")
        return path

    def _write_entry(self, entry: dict[str, Any]) -> Path:
        path = self._entry_path(str(entry["entry_id"]))
        self._atomic_write(path, json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
        return path

    def _write_ledger(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        now = self._now()
        existing = self.read_ledger()
        created_at = str(existing.get("created_at")) if existing else now
        ledger = {
            "created_at": created_at,
            "updated_at": now,
            "entry_count": len(entries),
            "entries": [
                {
                    "entry_id": entry["entry_id"],
                    "job_id": entry["job_id"],
                    "platform": entry["platform"],
                    "manual_upload_date": entry["manual_upload_date"],
                    "views": entry["metrics"]["views"],
                    "likes": entry["metrics"]["likes"],
                    "comments": entry["metrics"]["comments"],
                    "shares": entry["metrics"]["shares"],
                    "saves": entry["metrics"]["saves"],
                    "leads": entry["metrics"]["leads"],
                    "manual_upload_url": entry["manual_upload_url"],
                    "updated_at": entry["updated_at"],
                }
                for entry in entries
            ],
            "safety": dict(SAFETY_FLAGS),
        }
        self._atomic_write(
            self._ledger_path(),
            json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
        )
        return ledger

    def list_entries(self) -> list[dict[str, Any]]:
        if not self.entries_root.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(self.entries_root.glob("*.json")):
            value = self._read_json(path, path.name)
            self._validate_entry_shape(value)
            entries.append(value)
        return sorted(entries, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def read_entry(self, entry_id: str) -> dict[str, Any]:
        entry = self._read_json(self._entry_path(entry_id), f"entry {entry_id}")
        return self._validate_entry_shape(entry)

    def read_ledger(self) -> dict[str, Any] | None:
        path = self._ledger_path()
        if not path.is_file():
            return None
        value = self._read_json(path, LEDGER_FILENAME)
        safety = value.get("safety")
        if not isinstance(safety, dict):
            raise ResultsLedgerError("ledger safety block is missing")
        for key, expected in SAFETY_FLAGS.items():
            if safety.get(key) != expected:
                rendered = json.dumps(expected)
                raise ResultsLedgerError(f"ledger must state {key}: {rendered}")
        return value

    def summary_text(self) -> str:
        path = self._summary_path()
        if not path.is_file():
            return render_results_summary(self.list_entries())
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ResultsLedgerError("summary report is unreadable") from exc

    def entries_for_job(self, job_id: str) -> list[dict[str, Any]]:
        safe_id = validate_job_id(job_id)
        return [entry for entry in self.list_entries() if entry.get("job_id") == safe_id]

    def record_result(
        self,
        *,
        job_id: str,
        platform: str,
        manual_upload_url: str,
        metrics: dict[str, Any] | None = None,
        notes: str = "",
        manual_upload_date: str | None = None,
    ) -> ResultsLedgerResult:
        try:
            validation = validate_ready_job(
                job_id,
                export_root=self.export_root,
                output_root=self.output_root,
            )
            safe_platform = validate_platform(platform)
            safe_url = validate_url(manual_upload_url)
            safe_metrics = validate_metrics(metrics or {})
        except ResultsValidationError as exc:
            raise ResultsLedgerError(str(exc)) from exc
        now = self._now()
        entry = {
            "entry_id": self._entry_id(validation["job_id"], safe_platform),
            "created_at": now,
            "updated_at": now,
            "job_id": validation["job_id"],
            "platform": safe_platform,
            "manual_upload_url": safe_url,
            "manual_upload_date": manual_upload_date or self._today(),
            "metrics": safe_metrics,
            "context": self._build_context(validation),
            "notes": str(notes).strip(),
            "lessons": [],
            "source": "manual_entry",
            "safety": dict(SAFETY_FLAGS),
        }
        self._validate_entry_shape(entry)
        self._write_entry(entry)
        entries = self.list_entries()
        ledger = self._write_ledger(entries)
        summary_path = self._write_summary(entries)
        return ResultsLedgerResult(entry=entry, ledger=ledger, summary_path=summary_path)

    def update_result(
        self,
        entry_id: str,
        *,
        metrics: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> ResultsLedgerResult:
        entry = self.read_entry(entry_id)
        updated_metrics = dict(entry["metrics"])
        if metrics:
            updated_metrics.update(metrics)
        try:
            entry["metrics"] = validate_metrics(updated_metrics)
        except ResultsValidationError as exc:
            raise ResultsLedgerError(str(exc)) from exc
        if notes is not None:
            entry["notes"] = str(notes).strip()
        entry["updated_at"] = self._now()
        self._validate_entry_shape(entry)
        self._write_entry(entry)
        entries = self.list_entries()
        ledger = self._write_ledger(entries)
        summary_path = self._write_summary(entries)
        return ResultsLedgerResult(entry=entry, ledger=ledger, summary_path=summary_path)
