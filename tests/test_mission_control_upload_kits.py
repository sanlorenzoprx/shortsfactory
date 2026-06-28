import http.client
import json
import re
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server


def write_job(output_root: Path, job_id: str = "kit-job") -> None:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T19:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": {"name": "Kit idea"},
        "verdict": {"verdict_headline": "Test it"},
        "outputs": {},
        "warnings": [],
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (job_dir / "script.txt").write_text("Test this idea.\nTry it now.\n", encoding="utf-8")
    (job_dir / "short.mp4").write_bytes(b"video")


def write_export(export_root: Path, job_id: str = "kit-job") -> None:
    export_dir = export_root / "approved" / job_id
    export_dir.mkdir(parents=True)
    (export_dir / "EXPORT_MANIFEST.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "approval_state": "approved",
                "publishing_status": "not_published",
                "live_publishing_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    (export_dir / "APPROVAL.json").write_text(
        json.dumps({"job_id": job_id, "state": "approved"}), encoding="utf-8"
    )
    (export_dir / "receipt.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "idea": {"name": "Kit idea"},
                "verdict": {"verdict_headline": "<script>alert('kit')</script>"},
            }
        ),
        encoding="utf-8",
    )
    (export_dir / "script.txt").write_text("Test this idea.\nTry it now.\n", encoding="utf-8")
    (export_dir / "final.mp4").write_bytes(b"video")


def get_page(server, path: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        page = response.read().decode("utf-8")
        assert response.status == 200
        return page
    finally:
        connection.close()


def test_mission_control_requires_approved_export_before_upload_kit(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    write_job(output_root)
    server = create_server(output_root, "127.0.0.1", 0, export_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = get_page(server, "/jobs/kit-job")
        assert "Create an approved export bundle before making upload kits." in page
        assert "Create Manual Upload Kit" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_mission_control_builds_and_escapes_manual_upload_kit_without_publish_button(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    write_job(output_root)
    write_export(export_root)
    server = create_server(output_root, "127.0.0.1", 0, export_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        before = get_page(server, "/jobs/kit-job")
        assert "Create Manual Upload Kit" in before

        connection.request("POST", "/jobs/kit-job/upload-kit", body=b"")
        response = connection.getresponse()
        response.read()
        assert response.status == 303

        after = get_page(server, "/jobs/kit-job")
        assert "MANUAL UPLOAD ONLY - NOT PUBLISHED" in after
        assert "YouTube Shorts Manual Upload Checklist" in after
        assert "TikTok Manual Upload Checklist" in after
        assert "Instagram Reels Manual Upload Checklist" in after
        assert "Platform metadata" in after
        assert "&lt;script&gt;alert" in after
        assert "<script>alert" not in after
        assert not re.search(r"<button[^>]*>\s*Publish\s*</button>", after, re.IGNORECASE)
        assert (export_root / "upload_kits" / "kit-job" / "UPLOAD_KIT_MANIFEST.json").is_file()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
