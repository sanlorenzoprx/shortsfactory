from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from content_factory.config import Config


JobExecutor = Callable[[dict[str, Any]], Path]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


class LocalQueue:
    """A deliberately small, durable, single-process JSON queue."""

    def __init__(self, queue_path: Path, output_dir: Path):
        self.queue_path = queue_path
        self.output_dir = output_dir

    def enqueue(
        self,
        *,
        batch: int,
        locale: str,
        mode: str,
        record_app: bool = False,
        tts: bool = False,
        music: bool = False,
        publish_dry_run: bool = False,
        max_attempts: int = 3,
        scheduler: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if batch < 1:
            raise ValueError("batch must be >= 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        state = self._load()
        created: list[dict[str, Any]] = []
        for _ in range(batch):
            queue_id = uuid4().hex[:12]
            item = {
                "queue_id": queue_id,
                "output_job_id": f"q{queue_id[:11]}",
                "status": "pending",
                "locale": locale,
                "mode": mode,
                "record_app": bool(record_app),
                "tts": bool(tts),
                "music": bool(music),
                "publish_dry_run": bool(publish_dry_run),
                "attempt": 0,
                "max_attempts": max_attempts,
                "enqueued_at": _utc_now(),
                "started_at": None,
                "finished_at": None,
                "receipt_path": None,
                "error": None,
                "scheduler": deepcopy(scheduler),
            }
            state["jobs"].append(item)
            created.append(deepcopy(item))
        self._save(state)
        return created

    def list_jobs(self) -> list[dict[str, Any]]:
        return deepcopy(self._load()["jobs"])

    def run_pending(
        self, *, max_jobs: int = 1, executor: JobExecutor | None = None
    ) -> list[dict[str, Any]]:
        if max_jobs < 1:
            raise ValueError("max_jobs must be >= 1")
        executor = executor or self._execute_job
        initial = self._load()
        eligible_ids = [
            item["queue_id"]
            for item in initial["jobs"]
            if item["status"] in {"pending", "failed"}
            and item["attempt"] < item["max_attempts"]
        ][:max_jobs]
        completed: list[dict[str, Any]] = []

        for queue_id in eligible_ids:
            state = self._load()
            item = self._find(state, queue_id)
            item["status"] = "running"
            item["attempt"] += 1
            item["started_at"] = _utc_now()
            item["finished_at"] = None
            item["error"] = None
            self._save(state)

            try:
                receipt_path = executor(deepcopy(item))
                finished_at = _utc_now()
                self._patch_receipt(receipt_path, item, finished_at)
                state = self._load()
                item = self._find(state, queue_id)
                item["status"] = "succeeded"
                item["finished_at"] = finished_at
                item["receipt_path"] = str(receipt_path)
                item["error"] = None
                self._save(state)
            except Exception as exc:
                state = self._load()
                item = self._find(state, queue_id)
                item["status"] = "failed"
                item["finished_at"] = _utc_now()
                details = " ".join(str(exc).split()) or type(exc).__name__
                item["error"] = details[:500]
                self._save(state)
            completed.append(deepcopy(item))
        return completed

    def _execute_job(self, item: dict[str, Any]) -> Path:
        from orchestrator import ContentFactoryOrchestrator

        config = self.config_for_item(item)
        receipts = ContentFactoryOrchestrator(config).run_batch(
            batch=1,
            locale=item["locale"],
            job_id=item["output_job_id"],
        )
        return receipts[0]

    def config_for_item(self, item: dict[str, Any]) -> Config:
        return Config(
            mode=item["mode"],
            output_dir=self.output_dir,
            playwright_recording_enabled=item["record_app"],
            tts_enabled=item["tts"],
            music_enabled=item["music"],
            publish_dry_run_enabled=item.get("publish_dry_run", False),
        )

    @staticmethod
    def _patch_receipt(
        receipt_path: Path, item: dict[str, Any], finished_at: str
    ) -> None:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        payload["queue"] = {
            "status": "succeeded",
            "queue_id": item["queue_id"],
            "attempt": item["attempt"],
            "max_attempts": item["max_attempts"],
            "enqueued_at": item["enqueued_at"],
            "started_at": item["started_at"],
            "finished_at": finished_at,
        }
        if item.get("scheduler"):
            payload["scheduler"] = deepcopy(item["scheduler"])
        _write_json_atomic(receipt_path, payload)

    def _load(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            return {"version": 1, "jobs": []}
        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError(f"Invalid queue state: {self.queue_path}")
        return payload

    def _save(self, state: dict[str, Any]) -> None:
        _write_json_atomic(self.queue_path, state)

    @staticmethod
    def _find(state: dict[str, Any], queue_id: str) -> dict[str, Any]:
        for item in state["jobs"]:
            if item.get("queue_id") == queue_id:
                return item
        raise KeyError(f"Queue item not found: {queue_id}")


class LocalScheduler:
    """Reads one-shot local schedules; it never starts a daemon."""

    def __init__(self, schedule_path: Path, queue: LocalQueue):
        self.schedule_path = schedule_path
        self.queue = queue

    def preview_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        due = []
        for schedule in self._load()["schedules"]:
            if self._is_due(schedule, now):
                preview = deepcopy(schedule)
                preview["dry_run"] = True
                due.append(preview)
        return due

    def enqueue_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        state = self._load()
        created: list[dict[str, Any]] = []
        for schedule in state["schedules"]:
            if not self._is_due(schedule, now):
                continue
            scheduler = {
                "source": "local_schedule",
                "schedule_id": str(schedule["id"]),
                "dry_run": False,
            }
            created.extend(
                self.queue.enqueue(
                    batch=int(schedule.get("batch", 1)),
                    locale=str(schedule.get("locale", "en-US")),
                    mode=str(schedule.get("mode", "mock")),
                    record_app=bool(schedule.get("record_app", False)),
                    tts=bool(schedule.get("tts", False)),
                    music=bool(schedule.get("music", False)),
                    publish_dry_run=bool(schedule.get("publish_dry_run", False)),
                    max_attempts=int(schedule.get("max_attempts", 3)),
                    scheduler=scheduler,
                )
            )
            schedule["last_enqueued_at"] = now.isoformat()
        if created:
            _write_json_atomic(self.schedule_path, state)
        return created

    def _load(self) -> dict[str, Any]:
        if not self.schedule_path.exists():
            return {"version": 1, "schedules": []}
        payload = json.loads(self.schedule_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(
            payload.get("schedules"), list
        ):
            raise ValueError(f"Invalid schedule file: {self.schedule_path}")
        return payload

    @staticmethod
    def _is_due(schedule: dict[str, Any], now: datetime) -> bool:
        if not schedule.get("enabled", True) or schedule.get("last_enqueued_at"):
            return False
        due_at = schedule.get("due_at")
        if not due_at:
            return False
        parsed = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= now
