from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from content_factory.agents.publisher_agent import PLATFORMS, PublisherAgent
from content_factory.config import Config
from content_factory.local_queue import LocalQueue
from orchestrator import ContentFactoryOrchestrator, parse_args


def _fast_orchestrator(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> ContentFactoryOrchestrator:
    orchestrator = ContentFactoryOrchestrator(config)

    def create_short(_script, _verdict, job_dir: Path, **_kwargs) -> Path:
        path = job_dir / "short.mp4"
        path.write_bytes(b"publish-test-mp4")
        return path

    monkeypatch.setattr(orchestrator.video, "create_short", create_short)
    return orchestrator


def test_dry_run_packages_all_platforms_without_copying_video(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        publish_dry_run_enabled=True,
    )
    receipt_path = _fast_orchestrator(config, monkeypatch).run_batch(
        batch=1, locale="es-PR"
    )[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    job_dir = receipt_path.parent
    publish_dir = job_dir / "publish"

    assert receipt["publisher"] == {
        "status": "dry_run_ready",
        "live_publish_enabled": False,
        "platforms": list(PLATFORMS),
        "publisher_plan": "publish/publisher_plan.json",
        "warnings": [],
    }
    plan_path = Path(receipt["outputs"]["publisher_plan_json"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "dry_run_ready"
    assert plan["live_publish_enabled"] is False
    assert plan["requires_human_approval"] is True
    assert (plan_path.parent / plan["video"]).resolve().is_file()
    assert not list(publish_dir.rglob("*.mp4"))

    original_captions = Path(receipt["outputs"]["captions_srt"]).read_text(
        encoding="utf-8"
    )
    for platform in PLATFORMS:
        metadata_path = publish_dir / platform / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["status"] == "dry_run_ready"
        assert metadata["platform"] == platform
        assert metadata["source_job_id"] == receipt["job_id"]
        assert metadata["locale"] == "es-PR"
        assert metadata["title"]
        assert metadata["description"]
        assert metadata["caption"]
        assert metadata["hashtags"]
        assert metadata["live_publish_enabled"] is False
        assert (metadata_path.parent / metadata["video"]).resolve().is_file()
        assert (metadata_path.parent / metadata["thumbnail"]).resolve().is_file()
        copied_captions = (metadata_path.parent / metadata["captions"]).read_text(
            encoding="utf-8"
        )
        assert copied_captions == original_captions


def test_live_publish_is_explicitly_refused():
    with pytest.raises(RuntimeError, match="Live publishing is not implemented"):
        PublisherAgent.refuse_live_publish()


def test_queue_can_preserve_publish_dry_run_request(tmp_path):
    output_dir = tmp_path / "output"
    queue = LocalQueue(output_dir / "queue" / "jobs.json", output_dir)
    item = queue.enqueue(
        batch=1,
        locale="en-US",
        mode="mock",
        publish_dry_run=True,
    )[0]

    assert item["publish_dry_run"] is True
    assert queue.config_for_item(item).publish_dry_run_enabled is True


def test_publish_cli_flag_is_explicit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orchestrator.py"])
    assert parse_args().publish_dry_run is False

    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--publish-dry-run"])
    assert parse_args().publish_dry_run is True

    monkeypatch.setattr(
        sys,
        "argv",
        ["orchestrator.py", "--enqueue", "--publish-dry-run"],
    )
    args = parse_args()
    assert args.enqueue is True and args.publish_dry_run is True
