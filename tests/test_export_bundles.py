import http.client
import json
import threading
from pathlib import Path

import pytest

from content_factory.exporting.bundle_exporter import (
    BundleExportError,
    SUPPORTING_ARTIFACTS,
    export_approved_bundle,
)
from content_factory.mission_control.app import create_server
from content_factory.mission_control.job_index import find_job
from content_factory.mission_control.templates import render_job_detail


def write_job(
    output_root: Path,
    job_id: str = "job-123",
    videos: dict[str, bytes] | None = None,
) -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T16:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "warnings": [],
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    selected_videos = {"short.mp4": b"short-video"} if videos is None else videos
    for name, content in selected_videos.items():
        (job_dir / name).write_bytes(content)
    return job_dir


def write_approval(output_root: Path, job_id: str, state: str) -> Path:
    path = output_root / "approvals" / f"{job_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "state": state,
                "updated_at": "2026-06-28T16:01:00+00:00",
                "notes": "Human reviewed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_export_refuses_missing_approval(tmp_path):
    output_root = tmp_path / "output"
    write_job(output_root)

    with pytest.raises(BundleExportError, match="approval record is missing"):
        export_approved_bundle("job-123", output_root, tmp_path / "exports")


@pytest.mark.parametrize("state", ["pending", "rejected", "needs_revision"])
def test_export_refuses_non_approved_states(tmp_path, state):
    output_root = tmp_path / "output"
    write_job(output_root)
    write_approval(output_root, "job-123", state)

    with pytest.raises(BundleExportError, match=f"current state: {state}"):
        export_approved_bundle("job-123", output_root, tmp_path / "exports")


def test_approved_export_copies_artifacts_and_writes_safe_manifest(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    job_dir = write_job(
        output_root,
        videos={
            "short.mp4": b"short",
            "short_with_voice.mp4": b"voice",
            "short_with_music.mp4": b"music",
            "final.mp4": b"final",
        },
    )
    (job_dir / "thumbnail.jpg").write_bytes(b"jpeg")
    (job_dir / "captions.srt").write_text("captions", encoding="utf-8")
    (job_dir / "script.txt").write_text("script", encoding="utf-8")
    (job_dir / "app_recording.mp4").write_bytes(b"app")
    (job_dir / "app_recording_final.png").write_bytes(b"png")
    (job_dir / "lit_api_response.json").write_text("{}", encoding="utf-8")
    (job_dir / "publish").mkdir()
    (job_dir / "publish" / "publisher_plan.json").write_text(
        '{"live_publish_enabled": false}', encoding="utf-8"
    )
    approval_path = write_approval(output_root, "job-123", "approved")
    original_approval = approval_path.read_bytes()

    result = export_approved_bundle("job-123", output_root, export_root)

    assert result.export_dir == (export_root / "approved" / "job-123").resolve()
    assert (result.export_dir / "final.mp4").read_bytes() == b"final"
    assert (result.export_dir / "publisher_package.json").is_file()
    assert (result.export_dir / "APPROVAL.json").read_bytes() == original_approval
    assert approval_path.read_bytes() == original_approval
    manifest = json.loads((result.export_dir / "EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["approval_state"] == "approved"
    assert manifest["publishing_status"] == "not_published"
    assert manifest["live_publishing_enabled"] is False
    assert manifest["missing_optional_files"] == []
    assert set(manifest["included_files"]) == {
        "final.mp4",
        "thumbnail.jpg",
        "captions.srt",
        "script.txt",
        "receipt.json",
        "APPROVAL.json",
        "publisher_package.json",
        "app_recording.mp4",
        "app_recording_final.png",
        "lit_api_response.json",
    }


@pytest.mark.parametrize(
    ("videos", "expected"),
    [
        ({"final.mp4": b"final", "short_with_music.mp4": b"music"}, b"final"),
        ({"short_with_music.mp4": b"music", "short_with_voice.mp4": b"voice"}, b"music"),
        ({"short_with_voice.mp4": b"voice", "short.mp4": b"short"}, b"voice"),
        ({"short.mp4": b"short"}, b"short"),
    ],
)
def test_export_uses_best_available_video(tmp_path, videos, expected):
    output_root = tmp_path / "output"
    write_job(output_root, videos=videos)
    write_approval(output_root, "job-123", "approved")

    result = export_approved_bundle("job-123", output_root, tmp_path / "exports")

    assert (result.export_dir / "final.mp4").read_bytes() == expected


def test_export_refuses_job_without_video(tmp_path):
    output_root = tmp_path / "output"
    write_job(output_root, videos={})
    write_approval(output_root, "job-123", "approved")

    with pytest.raises(BundleExportError, match="no exportable MP4"):
        export_approved_bundle("job-123", output_root, tmp_path / "exports")


def test_missing_optional_assets_are_recorded_without_failure(tmp_path):
    output_root = tmp_path / "output"
    write_job(output_root)
    write_approval(output_root, "job-123", "approved")

    result = export_approved_bundle("job-123", output_root, tmp_path / "exports")

    assert result.manifest["missing_optional_files"] == list(SUPPORTING_ARTIFACTS)
    assert (result.export_dir / "receipt.json").is_file()
    assert (result.export_dir / "APPROVAL.json").is_file()


@pytest.mark.parametrize("job_id", ["../escape", "..", "nested/job", "nested\\job"])
def test_export_rejects_path_traversal(tmp_path, job_id):
    with pytest.raises(BundleExportError, match="invalid job_id"):
        export_approved_bundle(job_id, tmp_path / "output", tmp_path / "exports")


def test_repeated_export_cleanly_replaces_same_bundle(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    job_dir = write_job(output_root)
    write_approval(output_root, "job-123", "approved")
    first = export_approved_bundle("job-123", output_root, export_root)
    (first.export_dir / "stale.txt").write_text("remove me", encoding="utf-8")
    (job_dir / "short.mp4").write_bytes(b"updated-video")

    second = export_approved_bundle("job-123", output_root, export_root)

    assert second.export_dir == first.export_dir
    assert not (second.export_dir / "stale.txt").exists()
    assert (second.export_dir / "final.mp4").read_bytes() == b"updated-video"


def test_mission_control_only_offers_local_export_to_approved_jobs(tmp_path):
    output_root = tmp_path / "output"
    write_job(output_root)
    job = find_job(output_root, "job-123")

    pending_page = render_job_detail(job, {"state": "pending"})
    approved_page = render_job_detail(job, {"state": "approved"})

    assert "Approve this job before export." in pending_page
    assert "/jobs/job-123/export" not in pending_page
    assert "Export Approved Bundle" in approved_page
    assert 'method="post" action="/jobs/job-123/export"' in approved_page
    assert "does not publish or contact a platform" in approved_page
    assert ">Publish<" not in approved_page


def test_mission_control_export_post_creates_bundle_and_shows_manifest(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    write_job(output_root)
    write_approval(output_root, "job-123", "approved")
    server = create_server(output_root, "127.0.0.1", 0, export_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("POST", "/jobs/job-123/export", body=b"")
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        assert response.getheader("Location") == "/jobs/job-123"
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/jobs/job-123")
        detail = connection.getresponse()
        page = detail.read().decode("utf-8")
        assert detail.status == 200
        assert "Exported" in page
        assert "not_published" in page
        assert "live_publishing_enabled" in page
        assert (export_root / "approved" / "job-123" / "EXPORT_MANIFEST.json").is_file()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
