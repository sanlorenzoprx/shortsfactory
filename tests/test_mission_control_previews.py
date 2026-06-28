from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.previews.preview_models import PLATFORM_ORDER, SAFETY_FLAGS


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def create_sources(output_root: Path, export_root: Path, job_id: str = "preview-job") -> None:
    job = output_root / "jobs" / job_id
    job.mkdir(parents=True)
    receipt = {"job_id": job_id, "created_at": "2026-06-28T20:00:00+00:00", "locale": "en-US", "mode": "mock", "idea": {"name": "Preview"}, "verdict": {"verdict_headline": "Preview safely"}, "outputs": {}, "warnings": []}
    write_json(job / "receipt.json", receipt)
    (job / "script.txt").write_text("Test this preview.\nTry it now.", encoding="utf-8")
    (job / "short.mp4").write_bytes(b"video")
    ApprovalStore(output_root).write(job_id, "approved", "Preview approved export")

    export = export_root / "approved" / job_id
    export.mkdir(parents=True)
    write_json(export / "APPROVAL.json", {"job_id": job_id, "state": "approved"})
    write_json(export / "EXPORT_MANIFEST.json", {"job_id": job_id, "export_dir": str(export), "publishing_status": "not_published", "live_publishing_enabled": False})
    write_json(export / "receipt.json", {"job_id": job_id})
    (export / "final.mp4").write_bytes(b"video")

    kit = export_root / "upload_kits" / job_id
    write_json(kit / "UPLOAD_KIT_MANIFEST.json", {"job_id": job_id, "platforms": list(PLATFORM_ORDER), "upload_kit_dir": str(kit), **SAFETY_FLAGS})
    for platform in PLATFORM_ORDER:
        directory = kit / platform
        directory.mkdir(parents=True)
        write_json(directory / "platform_metadata.json", {"job_id": job_id, "platform": platform, "caption": "Safe metadata", "platform_dir": str(directory), **SAFETY_FLAGS})
        (directory / "upload_checklist.md").write_text("- [ ] Manual review", encoding="utf-8")
        (directory / "hashtags.txt").write_text("#shorts", encoding="utf-8")
        if platform == "youtube_shorts":
            (directory / "title.txt").write_text("<script>alert('x')</script>", encoding="utf-8")
            (directory / "description.txt").write_text("Description", encoding="utf-8")
        else:
            (directory / "caption.txt").write_text("Caption", encoding="utf-8")


def request(server, method: str, path: str) -> tuple[int, str, str | None]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request(method, path, body=b"")
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), response.getheader("Location")
    finally:
        connection.close()


def test_mission_control_generates_and_serves_safe_preview_cards(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_sources(output_root, export_root)
    server = create_server(output_root, "127.0.0.1", 0, export_root, tmp_path / "templates")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, before, _ = request(server, "GET", "/jobs/preview-job")
        assert status == 200
        assert "Generate Preview Cards" in before
        status, _, location = request(server, "POST", "/jobs/preview-job/preview-cards")
        assert status == 303
        assert location == "/jobs/preview-job"
        status, after, _ = request(server, "GET", "/jobs/preview-job")
        assert status == 200
        assert "Open Youtube Shorts Preview" in after
        assert "Open Tiktok Preview" in after
        assert "Open Instagram Reels Preview" in after
        assert "Open Preview Manifest" in after
        assert not re.search(r"<button[^>]*>\s*(Publish|Post|OAuth|Authorize|Connect account)", after, re.IGNORECASE)
        status, preview_html, _ = request(server, "GET", "/previews/preview-job/youtube_shorts_preview.html")
        assert status == 200
        assert "&lt;script&gt;alert" in preview_html
        assert "<script>alert" not in preview_html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
