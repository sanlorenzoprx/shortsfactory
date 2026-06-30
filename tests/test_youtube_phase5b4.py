from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from content_factory.autopilot.youtube_analytics import (
    COUNTRY_METRICS,
    PERFORMANCE_METRICS,
    AnalyticsUnsupportedError,
    YouTubeAnalyticsSnapshotter,
)
from content_factory.autopilot.youtube_publisher import (
    YOUTUBE_ANALYTICS_READONLY_SCOPE,
    YOUTUBE_REQUIRED_SCOPES,
    YouTubeCredentials,
)
from content_factory.autopilot.youtube_upload_index import YouTubeUploadIndex
from content_factory.autopilot.youtube_verification import YouTubeUploadVerifier


NOW = datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc)
CHANNEL_ID = "UCIzMYpBt3WdSXZBrvoE7eCg"
TOKEN = "phase5b4-fake-token-never-persist"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _fixture(tmp_path: Path, *, analytics_scope: bool = False) -> dict[str, Path | str]:
    output = tmp_path / "output"
    job_id = "ap-phase5b4-job"
    attempt_id = "ytu_phase5b4_test"
    video_id = "videoPhase5B4"
    job_dir = output / "jobs" / job_id
    video = job_dir / "short.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    metadata = _write(job_dir / "publish" / "youtube_shorts" / "metadata.json", {
        "schema_version": "youtube_upload_metadata.v1",
        "platform": "youtube_shorts",
        "source_job_id": job_id,
        "title": "Phase 5B.4 test",
        "description": "A safe test.",
        "privacy_status": "private",
        "made_for_kids": False,
    })
    metadata_hash = hashlib.sha256(metadata.read_bytes()).hexdigest()
    hardening = _write(
        output / "youtube" / "metadata_hardening" / job_id
        / "20260630T165000000000Z_YOUTUBE_METADATA_HARDENING.json",
        {
            "job_id": job_id,
            "timestamp": "2026-06-30T16:50:00+00:00",
            "metadata_path": str(metadata),
            "new_metadata_hash": metadata_hash,
            "secrets_recorded": False,
        },
    )
    preflight = _write(output / "youtube" / "credential_preflight" / "YOUTUBE_CREDENTIAL_PREFLIGHT.json", {
        "status": "passed",
        "paths": {"token": str(tmp_path / ".local" / "youtube" / "token.json")},
        "channel": {"status": "verified", "id": CHANNEL_ID, "title": "Ghost Town Test"},
        "token": {
            "youtube_upload_scope": True,
            "youtube_readonly_scope": True,
            "youtube_analytics_readonly_scope": analytics_scope,
        },
        "safety": {
            "upload_attempted": False,
            "videos_insert_called": False,
            "secrets_recorded": False,
        },
    })
    attempt_dir = output / "youtube" / "supervised_uploads" / attempt_id
    common = {
        "attempt_id": attempt_id,
        "timestamp": "2026-06-30T17:00:00+00:00",
        "channel": {"id": CHANNEL_ID, "title": "Ghost Town Test"},
        "selected_video_path": str(video),
        "metadata_summary": {
            "metadata_path": str(metadata),
            "schema_version": "youtube_upload_metadata.v1",
            "source_job_id": job_id,
            "title": "Phase 5B.4 test",
            "privacy_status": "private",
            "made_for_kids": False,
        },
        "source_receipt_references": {
            "credential_preflight": str(preflight),
            "metadata_hardening": None,
        },
        "upload_attempted": True,
        "secrets_recorded": False,
    }
    attempted = _write(attempt_dir / "01_attempted_live_upload.json", {
        **common,
        "classification": "attempted_live_upload",
        "videos_insert_called": False,
        "result": None,
    })
    successful = _write(attempt_dir / "02_successful_live_upload.json", {
        **common,
        "classification": "successful_live_upload",
        "videos_insert_called": True,
        "result": {
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "privacy_status": "private",
        },
    })
    return {
        "output": output,
        "job_id": job_id,
        "video_id": video_id,
        "metadata": metadata,
        "metadata_hash": metadata_hash,
        "hardening": hardening,
        "preflight": preflight,
        "attempted": attempted,
        "successful": successful,
    }


def _credentials(*, analytics: bool = False) -> YouTubeCredentials:
    scopes = YOUTUBE_REQUIRED_SCOPES + (
        (YOUTUBE_ANALYTICS_READONLY_SCOPE,) if analytics else ()
    )
    return YouTubeCredentials(
        access_token=TOKEN,
        scopes=scopes,
        expires_at="2026-07-02T18:00:00Z",
    )


class FakeVerificationTransport:
    name = "fake_videos_list"
    videos_insert_called = False

    def __init__(self, *, failure: Exception | None = None):
        self.calls: list[dict] = []
        self.videos_list_called = False
        self.failure = failure

    def videos_list(self, **kwargs):
        self.videos_list_called = True
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return {
            "items": [{
                "id": kwargs["video_id"],
                "snippet": {
                    "channelId": CHANNEL_ID,
                    "title": "Phase 5B.4 test",
                    "thumbnails": {"default": {"url": "https://img.example.test/video.jpg"}},
                },
                "status": {
                    "privacyStatus": "private",
                    "uploadStatus": "processed",
                    "embeddable": True,
                    "publicStatsViewable": True,
                },
                "contentDetails": {"duration": "PT45S"},
                "processingDetails": {"processingStatus": "succeeded"},
                "madeForKids": False,
                "selfDeclaredMadeForKids": False,
            }],
        }


class FakeAnalyticsTransport:
    name = "fake_youtube_analytics"
    videos_insert_called = False

    def __init__(self, *, empty: bool = False, unsupported: str | None = None):
        self.calls: list[dict] = []
        self.empty = empty
        self.unsupported = unsupported

    def query(self, **kwargs):
        self.calls.append(kwargs)
        report = "country" if kwargs["dimensions"] else "performance"
        if self.unsupported == report:
            raise AnalyticsUnsupportedError(f"unsupported {report} combination {TOKEN}")
        headers = [*kwargs["dimensions"], *kwargs["metrics"]]
        if self.empty:
            rows = []
        elif report == "country":
            rows = [["US", 12, 6.5, 32, 3], ["PR", 4, 2.0, 30, 1]]
        else:
            rows = [[16, 8.5, 31, 4, 2, 1]]
        return {"columnHeaders": [{"name": name} for name in headers], "rows": rows}


def test_upload_index_rebuild_is_idempotent_and_preserves_pointers(tmp_path):
    files = _fixture(tmp_path)
    index = YouTubeUploadIndex(output_root=files["output"], now=lambda: NOW)
    first = index.rebuild()
    second = index.rebuild()
    assert first == second
    assert len(first["uploads"]) == 1
    record = first["uploads"][0]
    assert record["youtube_video_id"] == files["video_id"]
    assert record["job_id"] == files["job_id"]
    assert record["metadata_hash"] == files["metadata_hash"]
    assert record["metadata_hardening_receipt"] == str(Path(files["hardening"]).resolve())
    assert record["upload_attempt_receipt"] == str(Path(files["attempted"]).resolve())
    assert record["upload_success_receipt"] == str(Path(files["successful"]).resolve())

    index.update(
        str(files["video_id"]),
        latest_verification_receipt="verification.json",
        latest_analytics_receipt="analytics.json",
    )
    rebuilt = index.rebuild()["uploads"][0]
    assert rebuilt["latest_verification_receipt"] == "verification.json"
    assert rebuilt["latest_analytics_receipt"] == "analytics.json"


def test_verification_blocks_before_transport_without_preflight(tmp_path):
    files = _fixture(tmp_path)
    Path(files["preflight"]).unlink()
    transport = FakeVerificationTransport()
    verifier = YouTubeUploadVerifier(
        output_root=files["output"],
        preflight_receipt=files["preflight"],
        transport=transport,
        credential_loader=lambda _: _credentials(),
        now=lambda: NOW,
    )
    receipt = verifier.verify(video_id=str(files["video_id"]), expected_channel_id=CHANNEL_ID)
    assert receipt["verification_status"] == "blocked"
    assert receipt["api_called"] is False
    assert receipt["videos_insert_called"] is False
    assert transport.calls == []
    assert Path(receipt["receipt_path"]).is_file()


def test_verification_blocks_channel_mismatch_before_transport(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeVerificationTransport()
    verifier = YouTubeUploadVerifier(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(), now=lambda: NOW,
    )
    receipt = verifier.verify(video_id=str(files["video_id"]), expected_channel_id="UC-wrong")
    assert receipt["verification_status"] == "blocked"
    assert transport.calls == []


def test_verification_uses_videos_list_writes_receipt_and_updates_index(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeVerificationTransport()
    verifier = YouTubeUploadVerifier(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(), now=lambda: NOW,
    )
    receipt = verifier.verify(
        success_receipt=files["successful"],
        expected_channel_id=CHANNEL_ID,
    )
    assert receipt["verification_status"] == "verified"
    assert receipt["request_type"] == "videos.list"
    assert receipt["parts_requested"] == ["snippet", "status", "contentDetails", "processingDetails"]
    assert receipt["duration"] == "PT45S"
    assert receipt["videos_insert_called"] is False
    assert len(transport.calls) == 1
    persisted = Path(receipt["receipt_path"]).read_text(encoding="utf-8")
    assert TOKEN not in persisted
    record = verifier.index.find(str(files["video_id"]))
    assert record["latest_verification_receipt"] == receipt["receipt_path"]
    assert record["last_verified_at"] == receipt["timestamp"]


def test_verification_failure_receipt_is_redacted(tmp_path):
    files = _fixture(tmp_path)
    transport = FakeVerificationTransport(
        failure=RuntimeError(f"Authorization: Bearer {TOKEN} https://accounts.google.com/o/oauth2/auth")
    )
    verifier = YouTubeUploadVerifier(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(), now=lambda: NOW,
    )
    receipt = verifier.verify(video_id=str(files["video_id"]), expected_channel_id=CHANNEL_ID)
    persisted = Path(receipt["receipt_path"]).read_text(encoding="utf-8")
    assert receipt["verification_status"] == "failed"
    assert TOKEN not in persisted
    assert "accounts.google.com" not in persisted
    assert receipt["videos_insert_called"] is False


def test_analytics_missing_scope_writes_two_blocked_receipts_without_api_call(tmp_path):
    files = _fixture(tmp_path, analytics_scope=False)
    transport = FakeAnalyticsTransport()
    snapshotter = YouTubeAnalyticsSnapshotter(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(), now=lambda: NOW,
    )
    results = snapshotter.snapshot(video_id=str(files["video_id"]), days=1)
    assert {row["snapshot_status"] for row in results.values()} == {"blocked_missing_analytics_scope"}
    assert transport.calls == []
    assert results["video_performance"]["receipt_path"].endswith("_YOUTUBE_ANALYTICS_SNAPSHOT.json")
    assert results["country_breakdown"]["receipt_path"].endswith("_YOUTUBE_COUNTRY_ANALYTICS_SNAPSHOT.json")
    assert all(row["api_called"] is False for row in results.values())
    assert all(row["videos_insert_called"] is False for row in results.values())


def test_analytics_writes_performance_and_country_snapshots_and_updates_index(tmp_path):
    files = _fixture(tmp_path, analytics_scope=True)
    transport = FakeAnalyticsTransport()
    snapshotter = YouTubeAnalyticsSnapshotter(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(analytics=True), now=lambda: NOW,
    )
    results = snapshotter.snapshot(video_id=str(files["video_id"]), days=1)
    performance = results["video_performance"]
    country = results["country_breakdown"]
    assert performance["snapshot_status"] == "available"
    assert performance["metrics_requested"] == list(PERFORMANCE_METRICS)
    assert performance["totals"]["shares"] == 1
    assert country["snapshot_status"] == "available"
    assert country["metrics_requested"] == list(COUNTRY_METRICS)
    assert country["dimensions_requested"] == ["country"]
    assert country["sort"] == "-views"
    assert country["max_results"] == 25
    assert country["rows"][0]["country"] == "US"
    assert len(transport.calls) == 2
    assert all(row["filters"] == f"video=={files['video_id']}" for row in transport.calls)
    assert all(result["videos_insert_called"] is False for result in results.values())
    record = snapshotter.index.find(str(files["video_id"]))
    assert record["latest_analytics_receipt"] == performance["receipt_path"]
    assert record["latest_country_analytics_receipt"] == country["receipt_path"]


def test_analytics_empty_rows_are_durable_empty_snapshots(tmp_path):
    files = _fixture(tmp_path, analytics_scope=True)
    snapshotter = YouTubeAnalyticsSnapshotter(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=FakeAnalyticsTransport(empty=True),
        credential_loader=lambda _: _credentials(analytics=True), now=lambda: NOW,
    )
    results = snapshotter.snapshot(video_id=str(files["video_id"]), days=7)
    assert {row["snapshot_status"] for row in results.values()} == {"empty"}
    assert all(row["rows"] == [] for row in results.values())
    assert all(Path(row["receipt_path"]).is_file() for row in results.values())


@pytest.mark.parametrize("unsupported", ["performance", "country"])
def test_unsupported_report_soft_blocks_without_losing_sibling_report(tmp_path, unsupported):
    files = _fixture(tmp_path, analytics_scope=True)
    transport = FakeAnalyticsTransport(unsupported=unsupported)
    snapshotter = YouTubeAnalyticsSnapshotter(
        output_root=files["output"], preflight_receipt=files["preflight"],
        transport=transport, credential_loader=lambda _: _credentials(analytics=True), now=lambda: NOW,
    )
    results = snapshotter.snapshot(video_id=str(files["video_id"]), days=28)
    blocked = "country_breakdown" if unsupported == "country" else "video_performance"
    available = "video_performance" if unsupported == "country" else "country_breakdown"
    assert results[available]["snapshot_status"] == "available"
    assert results[blocked]["snapshot_status"] == "blocked_or_unsupported"
    persisted = Path(results[blocked]["receipt_path"]).read_text(encoding="utf-8")
    assert TOKEN not in persisted
    assert len(transport.calls) == 2
    assert results[blocked]["videos_insert_called"] is False
