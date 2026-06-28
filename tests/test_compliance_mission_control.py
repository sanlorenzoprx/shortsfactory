from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server
from content_factory.mission_control.approvals import ApprovalStore

from tests.test_compliance_check import create_compliance_sources, write_json


def create_job(output_root: Path, export_root: Path, job_id: str = "compliance-job") -> None:
    job = output_root / "jobs" / job_id
    job.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T20:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": {"name": "Compliance"},
        "verdict": {"verdict_headline": "Review safely"},
        "outputs": {},
        "warnings": [],
    }
    write_json(job / "receipt.json", receipt)
    (job / "script.txt").write_text("Compliance test.", encoding="utf-8")
    (job / "short.mp4").write_bytes(b"video")
    ApprovalStore(output_root).write(job_id, "approved", "Approved for compliance")
    create_compliance_sources(
        export_root,
        job_id=job_id,
        youtube_title="TODO <title> safe review",
    )


def request(server, method: str, path: str) -> tuple[int, str, str | None]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request(method, path, body=b"")
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), response.getheader("Location")
    finally:
        connection.close()


def test_mission_control_shows_compliance_controls_and_safe_rendering(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_job(output_root, export_root)
    server = create_server(output_root, "127.0.0.1", 0, export_root, tmp_path / "templates")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, before, _ = request(server, "GET", "/jobs/compliance-job")
        assert status == 200
        assert "Generate Compliance Checklist" in before
        assert ">Publish<" not in before
        assert ">Post<" not in before
        assert "Upload automatically" not in before
        assert "Connect account" not in before
        assert "OAuth" not in before
        assert "Authorize platform" not in before
        status, _, location = request(server, "POST", "/jobs/compliance-job/compliance")
        assert status == 303
        assert location == "/jobs/compliance-job"
        status, after, _ = request(server, "GET", "/jobs/compliance-job")
        assert status == 200
        assert "Open Compliance Checklist" in after
        assert "Needs Human Review" in after
        assert "Machine checks" in after
        assert "Human review" in after
        assert "&lt;title&gt;" in after
        assert "placeholder text: <title>" not in after
        assert not re.search(r"<button[^>]*>\s*(Publish|Post|OAuth|Authorize|Connect account)", after, re.IGNORECASE)
        status, checklist_md, _ = request(server, "GET", "/compliance/compliance-job/COMPLIANCE_CHECKLIST.md")
        assert status == 200
        assert "Needs Human Review" in checklist_md
        status, _, location = request(server, "POST", "/jobs/compliance-job/compliance/review")
        assert status == 303
        assert location == "/jobs/compliance-job"
        status, reviewed_page, _ = request(server, "GET", "/jobs/compliance-job")
        assert status == 200
        assert "Ready for Manual Upload" in reviewed_page
        status, checklist_json, _ = request(server, "GET", "/compliance/compliance-job/COMPLIANCE_CHECKLIST.json")
        checklist = json.loads(checklist_json)
        assert checklist["ready_for_manual_upload"] is True
        assert checklist["review_method"] == "local_dashboard"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
