from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from content_factory.autopilot.supervised_youtube_upload import (
    EXPECTED_CHANNEL_ID,
    SupervisedYouTubeUploadGate,
)
from content_factory.autopilot.youtube_publisher import (
    YOUTUBE_REQUIRED_SCOPES,
    YouTubeCredentials,
    YouTubeUploadPayload,
)


NOW = datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc)
TOKEN = "test-supervised-token-never-persist"


class FakeTransport:
    name = "fake_supervised_transport"

    def __init__(self, output_root: Path, *, failure: Exception | None = None):
        self.output_root = output_root
        self.failure = failure
        self.calls: list[dict] = []
        self.receipts_seen_during_call: list[Path] = []
        self.videos_insert_called = False

    def upload(self, *, access_token: str, payload: YouTubeUploadPayload) -> dict:
        self.receipts_seen_during_call = list(
            (self.output_root / "youtube" / "supervised_uploads").glob("*/01_attempted_live_upload.json")
        )
        self.calls.append({"access_token": access_token, "payload": payload})
        self.videos_insert_called = True
        if self.failure:
            raise self.failure
        return {"id": "supervised-video-123"}


def _write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    output = tmp_path / "output"
    job_id = "ap-supervised-job"
    idea_id = "idea-supervised"
    job_dir = output / "jobs" / job_id
    video = job_dir / "short.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"generated-video")
    generation = _write(job_dir / "receipt.json", {
        "job_id": job_id,
        "mode": "mock",
        "outputs": {"short_mp4": str(video)},
        "verdict": {
            "verdict_headline": "Build the test",
            "lit_score": 84,
            "risk_level": "medium",
            "top_reason": "Demand can be tested.",
            "next_step": "Run the smallest paid pilot.",
        },
    })
    metadata = _write(job_dir / "publish" / "youtube_shorts" / "metadata.json", {
        "status": "dry_run_ready",
        "live_publish_enabled": False,
        "platform": "youtube_shorts",
        "source_job_id": job_id,
        "locale": "en-US",
        "title": "A supervised first upload",
        "description": "Validate one painful use case before building.",
        "hashtags": ["#Shorts", "#Validation"],
        "video": "../../short.mp4",
        "made_for_kids": False,
        "privacy_status": "private",
        "notify_subscribers": False,
    })
    plan = _write(job_dir / "publish" / "publisher_plan.json", {
        "status": "dry_run_ready",
        "live_publish_enabled": False,
        "requires_human_approval": True,
        "source_job_id": job_id,
        "platforms": {"youtube_shorts": "youtube_shorts/metadata.json"},
    })
    batch = output / "autopilot" / "batches" / "ap_supervised_fixture"
    _write(batch / "generated_jobs.json", [{
        "job_id": job_id,
        "idea_id": idea_id,
        "receipt_path": str(generation),
        "job_dir": str(job_dir),
        "publisher_plan": str(plan),
    }])
    _write(batch / "lit_verdicts.json", [{
        "idea_id": idea_id,
        "verdict": {
            "verdict_headline": "Build the test",
            "lit_score": 84,
            "risk_level": "medium",
            "top_reason": "Demand can be tested.",
            "next_step": "Run the smallest paid pilot.",
        },
    }])
    _write(batch / "quality_gates.json", [{
        "job_id": job_id,
        "gate_name": "quality",
        "status": "pass",
        "blocking": False,
        "reason": "quality score 96 meets machine policy",
    }])
    _write(batch / "compliance_gates.json", [{
        "job_id": job_id,
        "gate_name": "compliance",
        "status": "pass",
        "blocking": False,
        "reason": "autopilot compliance policy passed",
    }])
    _write(batch / "AUTOPILOT_RECEIPT.json", {
        "batch_id": batch.name,
        "mode": "dry_run",
        "status": "completed",
        "safety": {"simulated_publishing_only": True},
    })
    token = _write(tmp_path / ".local" / "youtube" / "token.json", {"token": TOKEN})
    preflight = _write(output / "youtube" / "credential_preflight" / "YOUTUBE_CREDENTIAL_PREFLIGHT.json", {
        "receipt_version": "phase5b.1.youtube-credentials.v1",
        "status": "passed",
        "paths": {"token": str(token)},
        "checks": [
            {"name": "youtube_upload_scope", "passed": True},
            {"name": "youtube_readonly_scope", "passed": True},
            {"name": "channel_identity", "passed": True},
        ],
        "token": {"youtube_upload_scope": True, "youtube_readonly_scope": True},
        "channel": {"status": "verified", "id": EXPECTED_CHANNEL_ID, "title": "Ghost Town Test"},
        "safety": {
            "upload_attempted": False,
            "videos_insert_called": False,
            "secrets_recorded": False,
        },
    })
    return {
        "output": output,
        "video": video,
        "metadata": metadata,
        "generation": generation,
        "batch": batch,
        "preflight": preflight,
        "job_id": job_id,
    }


def _credentials(_token_path: Path) -> YouTubeCredentials:
    return YouTubeCredentials(
        access_token=TOKEN,
        scopes=YOUTUBE_REQUIRED_SCOPES,
        expires_at="2026-07-01T15:00:00Z",
    )


def _run(files: dict[str, Path | str], transport: FakeTransport, **updates):
    values = {
        "videos": [files["video"]],
        "metadata_path": files["metadata"],
        "confirm_channel_id": EXPECTED_CHANNEL_ID,
        "confirm_live_upload": True,
        "confirm_quota_reviewed": True,
        "confirm_policy_reviewed": True,
    }
    values.update(updates)
    gate = SupervisedYouTubeUploadGate(
        output_root=files["output"],
        preflight_receipt=files["preflight"],
        transport=transport,
        credential_loader=_credentials,
        now=lambda: NOW,
    )
    return gate.run(**values)


@pytest.mark.parametrize("missing", [
    "confirm_live_upload",
    "confirm_quota_reviewed",
    "confirm_policy_reviewed",
])
def test_each_explicit_approval_is_required(tmp_path, missing):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    result = _run(files, transport, **{missing: False})
    assert result.classification == "blocked_missing_approval"
    assert transport.calls == []


def test_missing_preflight_is_refused(tmp_path):
    files = _fixture(tmp_path)
    Path(files["preflight"]).unlink()
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_missing_preflight"
    assert transport.calls == []


@pytest.mark.parametrize(("section", "key", "value"), [
    (None, "status", "blocked"),
    ("safety", "upload_attempted", True),
    ("safety", "videos_insert_called", True),
    ("safety", "secrets_recorded", True),
])
def test_failed_or_used_preflight_is_refused(tmp_path, section, key, value):
    files = _fixture(tmp_path)
    preflight_path = Path(files["preflight"])
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    target = preflight if section is None else preflight[section]
    target[key] = value
    _write(preflight_path, preflight)
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_missing_preflight"
    assert transport.calls == []


def test_channel_mismatch_is_refused(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    result = _run(files, transport, confirm_channel_id="UC-wrong-channel")
    assert result.classification == "blocked_channel_mismatch"
    assert transport.calls == []


def test_missing_video_directory_and_batch_selection_are_refused(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    missing = _run(files, transport, videos=[tmp_path / "missing.mp4"])
    directory = _run(files, transport, videos=[Path(files["video"]).parent])
    batch = _run(files, transport, videos=[files["video"], files["video"]])
    assert missing.classification == "blocked_missing_video"
    assert directory.classification == "blocked_missing_video"
    assert batch.classification == "blocked_missing_video"
    assert transport.calls == []


def test_arbitrary_mp4_and_missing_generation_receipt_are_refused(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    rogue = Path(files["video"]).with_name("rogue.mp4")
    rogue.write_bytes(b"not-listed")
    arbitrary = _run(files, transport, videos=[rogue])
    assert arbitrary.classification == "blocked_untrusted_video"
    Path(files["generation"]).unlink()
    missing_receipt = _run(files, transport)
    assert missing_receipt.classification == "blocked_untrusted_video"
    assert transport.calls == []


def test_missing_lit_verdict_is_refused(tmp_path):
    files = _fixture(tmp_path)
    (Path(files["batch"]) / "lit_verdicts.json").unlink()
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_missing_lit_verdict"
    assert transport.calls == []


@pytest.mark.parametrize("name", ["quality_gates.json", "compliance_gates.json"])
def test_missing_quality_or_compliance_gate_is_refused(tmp_path, name):
    files = _fixture(tmp_path)
    (Path(files["batch"]) / name).unlink()
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_missing_quality_gate"
    assert transport.calls == []


def test_invalid_metadata_is_refused_before_transport(tmp_path):
    files = _fixture(tmp_path)
    metadata = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
    metadata["title"] = ""
    _write(Path(files["metadata"]), metadata)
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_invalid_metadata"
    assert transport.calls == []


def test_scheduled_non_private_metadata_is_refused(tmp_path):
    files = _fixture(tmp_path)
    metadata = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
    metadata["privacy_status"] = "public"
    metadata["publish_at"] = "2026-07-01T15:00:00Z"
    _write(Path(files["metadata"]), metadata)
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "blocked_invalid_metadata"
    assert transport.calls == []


def test_transport_is_reached_only_after_all_gates_and_attempt_receipt(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    result = _run(files, transport)
    assert result.classification == "successful_live_upload"
    assert len(transport.calls) == 1
    assert len(transport.receipts_seen_during_call) == 1
    assert len(result.receipt_paths) == 2
    assert result.receipt_paths[0].endswith("01_attempted_live_upload.json")
    assert result.receipt_paths[1].endswith("02_successful_live_upload.json")
    attempted = json.loads(Path(result.receipt_paths[0]).read_text(encoding="utf-8"))
    successful = json.loads(Path(result.receipt_paths[1]).read_text(encoding="utf-8"))
    assert attempted["upload_attempted"] is True
    assert attempted["videos_insert_called"] is False
    assert successful["upload_attempted"] is True
    assert successful["videos_insert_called"] is True
    assert successful["result"]["video_id"] == "supervised-video-123"
    assert Path(result.receipt_paths[0]).is_file()


def test_transport_failure_preserves_attempt_and_writes_redacted_failure(tmp_path):
    files = _fixture(tmp_path)
    failure = RuntimeError(
        f"Authorization: Bearer {TOKEN} access_token={TOKEN} "
        "https://accounts.google.com/o/oauth2/auth?code=secret-code"
    )
    transport = FakeTransport(files["output"], failure=failure)
    result = _run(files, transport)
    assert result.classification == "failed_live_upload"
    assert len(result.receipt_paths) == 2
    assert result.receipt_paths[0].endswith("01_attempted_live_upload.json")
    assert result.receipt_paths[1].endswith("02_failed_live_upload.json")
    persisted = "\n".join(Path(path).read_text(encoding="utf-8") for path in result.receipt_paths)
    assert TOKEN not in persisted
    assert "secret-code" not in persisted
    assert "accounts.google.com" not in persisted
    assert '"secrets_recorded": false' in persisted


def test_blocked_receipt_records_safe_evidence_without_transport(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeTransport(files["output"])
    result = _run(files, transport, confirm_live_upload=False)
    receipt = json.loads(Path(result.receipt_paths[0]).read_text(encoding="utf-8"))
    assert receipt["classification"] == "blocked_missing_approval"
    assert receipt["upload_attempted"] is False
    assert receipt["videos_insert_called"] is False
    assert receipt["secrets_recorded"] is False
    assert transport.calls == []
