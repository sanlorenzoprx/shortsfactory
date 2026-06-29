from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from content_factory.autopilot.autopilot_config import AutopilotConfig
from content_factory.autopilot.autopilot_models import PublishAttempt
from content_factory.autopilot.publisher_adapters import SimulatedPublisherAdapter
from content_factory.autopilot.youtube_publisher import (
    YOUTUBE_REQUIRED_SCOPES,
    YouTubeCredentials,
    YouTubeLivePolicy,
    YouTubePublisherAdapter,
    YouTubeUploadPayload,
)


NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


class FakeTransport:
    name = "fake_youtube_transport"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload(self, *, access_token: str, payload: YouTubeUploadPayload) -> dict:
        self.calls.append({"access_token": access_token, "payload": payload})
        return {"id": "youtube-video-123"}


def _attempt(metadata_path: Path, *, mode: str = "full_autopilot") -> PublishAttempt:
    return PublishAttempt(
        publish_attempt_id="pub_youtube_test",
        batch_id="ap_youtube_test",
        job_id="youtube-job",
        platform="youtube_shorts",
        mode=mode,
        adapter="youtube_official",
        status="queued",
        external_post_id=None,
        external_url=None,
        blocked_reason=None,
        metadata_path=str(metadata_path.resolve()),
        created_at=NOW.isoformat(),
        finished_at=None,
    )


def _publisher_files(tmp_path: Path, **updates) -> Path:
    job_dir = tmp_path / "jobs" / "youtube-job"
    publish_dir = job_dir / "publish"
    platform_dir = publish_dir / "youtube_shorts"
    platform_dir.mkdir(parents=True)
    (job_dir / "short.mp4").write_bytes(b"local-video-fixture")
    metadata = {
        "status": "live_ready",
        "live_publish_enabled": True,
        "approved_for_live_publish": True,
        "platform": "youtube_shorts",
        "source_job_id": "youtube-job",
        "locale": "en-US",
        "title": "A narrow business test",
        "description": "Validate one painful use case before building.",
        "hashtags": ["#Shorts", "#Validation"],
        "video": "../../short.mp4",
        "made_for_kids": False,
        "privacy_status": "private",
        "notify_subscribers": False,
    }
    metadata.update(updates)
    metadata_path = platform_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    plan_path = publish_dir / "publisher_plan.json"
    plan_path.write_text(json.dumps({
        "source_job_id": "youtube-job",
        "live_publish_enabled": True,
        "approved_for_live_publish": True,
        "platforms": {"youtube_shorts": "youtube_shorts/metadata.json"},
    }), encoding="utf-8")
    return plan_path


def _credentials() -> YouTubeCredentials:
    return YouTubeCredentials(
        access_token="test-token-not-real",
        scopes=YOUTUBE_REQUIRED_SCOPES,
        expires_at="2026-06-30T12:00:00Z",
    )


def _policy() -> YouTubeLivePolicy:
    return YouTubeLivePolicy(
        live_publishing_enabled=True,
        youtube_publishing_enabled=True,
        quota_remaining=1,
        policy_acknowledged=True,
        credential_preflight_ready=True,
    )


def test_dry_run_still_never_reads_youtube_credentials(tmp_path):
    credential_reads = 0

    def credentials_that_must_not_be_read():
        nonlocal credential_reads
        credential_reads += 1
        raise AssertionError("dry_run attempted to read YouTube credentials")

    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credential_loader=credentials_that_must_not_be_read,
        now=lambda: NOW,
    )
    preflight = adapter.preflight(config=AutopilotConfig(mode="dry_run"))
    assert preflight["ready"] is False
    assert preflight["credentials_checked"] is False
    assert credential_reads == 0

    simulated = SimulatedPublisherAdapter("youtube_shorts")
    metadata = tmp_path / "publisher_plan.json"
    attempt = _attempt(metadata, mode="dry_run")
    result = simulated.publish(
        attempt=attempt,
        package={"metadata_path": attempt.metadata_path},
    )
    assert result.status == "simulated_success"
    assert credential_reads == 0


def test_live_mode_refuses_without_credentials_and_writes_receipt(tmp_path):
    metadata = _publisher_files(tmp_path)
    transport = FakeTransport()
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credentials=YouTubeCredentials(),
        policy=_policy(),
        transport=transport,
        now=lambda: NOW,
    )
    result = adapter.publish(
        attempt=_attempt(metadata),
        package={"metadata_path": str(metadata.resolve())},
    )
    assert result.status == "blocked"
    assert "oauth_access_token" in result.blocked_reason
    assert transport.calls == []
    receipt = json.loads(adapter.last_receipt_path.read_text(encoding="utf-8"))
    assert receipt["classification"] == "blocked_live_publish"
    assert receipt["api_call_attempted"] is False
    assert receipt["credentials_recorded"] is False


def test_invalid_metadata_is_blocked_before_api_call(tmp_path):
    metadata = _publisher_files(tmp_path, title="", approved_for_live_publish=False)
    transport = FakeTransport()
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credentials=_credentials(),
        policy=_policy(),
        transport=transport,
        now=lambda: NOW,
    )
    result = adapter.publish(
        attempt=_attempt(metadata),
        package={"metadata_path": str(metadata.resolve())},
    )
    assert result.status == "blocked"
    assert "not approved" in result.blocked_reason
    assert transport.calls == []
    receipt = json.loads(adapter.last_receipt_path.read_text(encoding="utf-8"))
    assert receipt["api_call_attempted"] is False
    assert receipt["payload"] is None


def test_dry_run_publisher_plan_is_blocked_before_api_call(tmp_path):
    metadata = _publisher_files(tmp_path)
    plan = json.loads(metadata.read_text(encoding="utf-8"))
    plan["live_publish_enabled"] = False
    metadata.write_text(json.dumps(plan), encoding="utf-8")
    transport = FakeTransport()
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credentials=_credentials(),
        policy=_policy(),
        transport=transport,
        now=lambda: NOW,
    )
    result = adapter.publish(
        attempt=_attempt(metadata),
        package={"metadata_path": str(metadata.resolve())},
    )
    assert result.status == "blocked"
    assert "publisher plan does not explicitly enable" in result.blocked_reason
    assert transport.calls == []


def test_scheduled_upload_payload_is_private_and_future(tmp_path):
    metadata = _publisher_files(
        tmp_path,
        schedule_window={"publish_at": "2026-06-30T09:30:00-04:00"},
        privacy_status="private",
    )
    transport = FakeTransport()
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credentials=_credentials(),
        policy=_policy(),
        transport=transport,
        now=lambda: NOW,
    )
    result = adapter.publish(
        attempt=_attempt(metadata),
        package={"metadata_path": str(metadata.resolve())},
    )
    assert result.status == "published"
    payload = transport.calls[0]["payload"]
    assert payload.body["status"] == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "publishAt": "2026-06-30T13:30:00Z",
    }


def test_successful_adapter_path_creates_durable_receipt_without_real_upload(tmp_path):
    metadata = _publisher_files(tmp_path)
    transport = FakeTransport()
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path / "output root with spaces",
        credentials=_credentials(),
        policy=_policy(),
        transport=transport,
        now=lambda: NOW,
    )
    attempt = _attempt(metadata)
    result = adapter.publish(
        attempt=attempt,
        package={"metadata_path": attempt.metadata_path},
    )
    assert result.status == "published"
    assert result.external_post_id == "youtube-video-123"
    assert result.external_url == "https://www.youtube.com/watch?v=youtube-video-123"
    assert len(transport.calls) == 1

    expected = (
        tmp_path / "output root with spaces" / "autopilot" / "batches"
        / attempt.batch_id / "publisher_receipts" / "youtube_shorts"
        / f"{attempt.publish_attempt_id}.json"
    ).resolve()
    assert adapter.last_receipt_path == expected
    receipt = json.loads(expected.read_text(encoding="utf-8"))
    assert receipt["classification"] == "successful_live_publish_adapter_path"
    assert receipt["attempt"]["status"] == "published"
    assert receipt["api_call_attempted"] is True
    assert receipt["oauth_required"] is True
    assert receipt["quota_check_required"] is True
    assert receipt["platform_policy_check_required"] is True
    assert "test-token-not-real" not in expected.read_text(encoding="utf-8")


def test_live_preflight_blocks_quota_and_policy_gates(tmp_path):
    adapter = YouTubePublisherAdapter(
        output_root=tmp_path,
        credentials=_credentials(),
        policy=YouTubeLivePolicy(
            live_publishing_enabled=True,
            youtube_publishing_enabled=True,
            quota_remaining=0,
            policy_acknowledged=False,
            emergency_stop=True,
        ),
        transport=FakeTransport(),
        now=lambda: NOW,
    )
    preflight = adapter.preflight(config=AutopilotConfig(mode="full_autopilot"))
    assert preflight["ready"] is False
    assert "emergency_stop_clear" in preflight["reason"]
    assert "youtube_upload_quota_available" in preflight["reason"]
    assert "youtube_policy_acknowledged" in preflight["reason"]
