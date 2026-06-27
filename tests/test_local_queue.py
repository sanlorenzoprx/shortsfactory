from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from content_factory.local_queue import LocalQueue, LocalScheduler
from orchestrator import parse_args


REQUIRED_OUTPUTS = (
    "short_mp4",
    "thumbnail_jpg",
    "captions_srt",
    "script_txt",
    "verdict_json",
    "idea_json",
)


def _artifact_executor(output_dir: Path, calls: list[str]):
    def execute(item):
        calls.append(item["queue_id"])
        job_dir = output_dir / "jobs" / item["output_job_id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        outputs = {}
        filenames = {
            "short_mp4": "short.mp4",
            "thumbnail_jpg": "thumbnail.jpg",
            "captions_srt": "captions.srt",
            "script_txt": "script.txt",
            "verdict_json": "verdict.json",
            "idea_json": "idea.json",
        }
        for key, filename in filenames.items():
            path = job_dir / filename
            path.write_bytes(f"queue artifact {key}".encode("utf-8"))
            outputs[key] = str(path)
        receipt_path = job_dir / "receipt.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "job_id": item["output_job_id"],
                    "outputs": outputs,
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        return receipt_path

    return execute


def test_queue_enqueues_three_jobs_and_state_is_durable(tmp_path):
    output_dir = tmp_path / "output"
    queue_path = output_dir / "queue" / "jobs.json"
    queue = LocalQueue(queue_path, output_dir)
    created = queue.enqueue(batch=3, locale="en-US", mode="mock")

    assert len(created) == 3
    assert queue_path.exists()
    assert all(item["status"] == "pending" for item in created)
    reloaded = LocalQueue(queue_path, output_dir).list_jobs()
    assert [item["queue_id"] for item in reloaded] == [
        item["queue_id"] for item in created
    ]


def test_worker_runs_jobs_writes_artifacts_and_receipt_metadata(tmp_path):
    output_dir = tmp_path / "output"
    queue = LocalQueue(output_dir / "queue" / "jobs.json", output_dir)
    queue.enqueue(batch=3, locale="es-PR", mode="mock")
    calls: list[str] = []

    completed = queue.run_pending(
        max_jobs=3, executor=_artifact_executor(output_dir, calls)
    )

    assert len(completed) == 3
    assert all(item["status"] == "succeeded" for item in completed)
    assert len(calls) == 3
    for item in completed:
        receipt_path = Path(item["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["queue"]["status"] == "succeeded"
        assert receipt["queue"]["queue_id"] == item["queue_id"]
        assert receipt["queue"]["attempt"] == 1
        for key in REQUIRED_OUTPUTS:
            path = Path(receipt["outputs"][key])
            assert path.exists() and path.stat().st_size > 0


def test_failed_job_retries_only_to_cap(tmp_path):
    output_dir = tmp_path / "output"
    queue = LocalQueue(output_dir / "queue" / "jobs.json", output_dir)
    queue.enqueue(batch=1, locale="en-US", mode="mock", max_attempts=2)
    calls = []

    def fail(item):
        calls.append(item["attempt"])
        raise RuntimeError("controlled queue failure")

    queue.run_pending(max_jobs=1, executor=fail)
    queue.run_pending(max_jobs=1, executor=fail)
    assert queue.run_pending(max_jobs=1, executor=fail) == []
    item = queue.list_jobs()[0]
    assert calls == [1, 2]
    assert item["status"] == "failed"
    assert item["attempt"] == 2
    assert item["error"] == "controlled queue failure"


def test_succeeded_job_is_not_duplicated_on_rerun(tmp_path):
    output_dir = tmp_path / "output"
    queue = LocalQueue(output_dir / "queue" / "jobs.json", output_dir)
    created = queue.enqueue(batch=1, locale="en-US", mode="mock")[0]
    calls: list[str] = []
    executor = _artifact_executor(output_dir, calls)

    queue.run_pending(max_jobs=1, executor=executor)
    assert queue.run_pending(max_jobs=1, executor=executor) == []
    assert calls == [created["queue_id"]]
    assert len(list((output_dir / "jobs").iterdir())) == 1


def test_schedule_dry_run_does_not_enqueue_or_create_job_outputs(tmp_path):
    output_dir = tmp_path / "output"
    queue_path = output_dir / "queue" / "jobs.json"
    schedule_path = output_dir / "schedules" / "schedules.json"
    schedule_path.parent.mkdir(parents=True)
    schedule_path.write_text(
        json.dumps(
            {
                "version": 1,
                "schedules": [
                    {
                        "id": "morning-es",
                        "enabled": True,
                        "due_at": "2020-01-01T00:00:00+00:00",
                        "locale": "es-PR",
                        "mode": "mock",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    queue = LocalQueue(queue_path, output_dir)
    scheduler = LocalScheduler(schedule_path, queue)

    due = scheduler.preview_due(datetime.now(timezone.utc))

    assert [item["id"] for item in due] == ["morning-es"]
    assert due[0]["dry_run"] is True
    assert not queue_path.exists()
    assert not (output_dir / "jobs").exists()


def test_run_due_adds_scheduler_metadata_to_completed_receipt(tmp_path):
    output_dir = tmp_path / "output"
    schedule_path = output_dir / "schedules" / "schedules.json"
    schedule_path.parent.mkdir(parents=True)
    schedule_path.write_text(
        json.dumps(
            {
                "version": 1,
                "schedules": [
                    {
                        "id": "one-shot",
                        "due_at": "2020-01-01T00:00:00+00:00",
                        "locale": "en-US",
                        "mode": "mock",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    queue = LocalQueue(output_dir / "queue" / "jobs.json", output_dir)
    scheduler = LocalScheduler(schedule_path, queue)
    created = scheduler.enqueue_due()
    completed = queue.run_pending(
        max_jobs=1, executor=_artifact_executor(output_dir, [])
    )
    receipt = json.loads(
        Path(completed[0]["receipt_path"]).read_text(encoding="utf-8")
    )

    assert len(created) == 1
    assert receipt["scheduler"] == {
        "source": "local_schedule",
        "schedule_id": "one-shot",
        "dry_run": False,
    }
    assert scheduler.enqueue_due() == []


def test_queue_cli_actions_are_explicit(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["orchestrator.py", "--enqueue", "--batch", "3"]
    )
    args = parse_args()
    assert args.enqueue is True and args.batch == 3

    monkeypatch.setattr(
        sys, "argv", ["orchestrator.py", "--run-queue", "--max-jobs", "2"]
    )
    args = parse_args()
    assert args.run_queue is True and args.max_jobs == 2

    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--schedule-dry-run"])
    assert parse_args().schedule_dry_run is True
