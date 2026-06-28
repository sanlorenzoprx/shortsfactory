import http.client
import json
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server
from content_factory.mission_control.job_index import find_job
from content_factory.mission_control.templates import render_index, render_job_detail
from content_factory.quality.quality_store import QualityStore


def write_quality_job(output_root: Path) -> Path:
    job_dir = output_root / "jobs" / "quality-job"
    job_dir.mkdir(parents=True)
    script = (
        "Test this idea before you build.\n"
        "Score: 82/100.\nRisk: medium.\nVerdict: promising.\n"
        "Test this idea now, then decide what to build.\n"
    )
    receipt = {
        "job_id": "quality-job",
        "created_at": "2026-06-28T18:10:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": {"name": "Quality idea"},
        "verdict": {"verdict_headline": "Promising"},
        "outputs": {},
        "warnings": [],
        "recording": {"enabled": False},
        "voiceover": {"status": "disabled"},
        "music": {"status": "disabled"},
        "publisher": {"status": "disabled"},
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (job_dir / "script.txt").write_text(script, encoding="utf-8")
    (job_dir / "captions.srt").write_text(
        f"1\n00:00:00,000 --> 00:00:30,000\n{script}", encoding="utf-8"
    )
    (job_dir / "thumbnail.jpg").write_bytes(b"jpeg")
    (job_dir / "short.mp4").write_bytes(b"video")
    return job_dir


def test_mission_control_escapes_quality_issues_and_displays_status(tmp_path):
    output_root = tmp_path / "output"
    write_quality_job(output_root)
    job = find_job(output_root, "quality-job")
    report = {
        "job_id": "quality-job",
        "overall_score": 65,
        "status": "warn",
        "approval_ready": False,
        "export_ready": False,
        "recommended_action": "revise",
        "category_scores": {"hook": 55, "cta": 40},
        "issues": [
            {
                "severity": "warning",
                "category": "hook",
                "message": "<script>alert('quality')</script>",
                "suggested_fix": "<img src=x onerror=alert(1)>",
            }
        ],
    }

    detail = render_job_detail(job, {"state": "pending"}, quality_report=report)
    index = render_index([job], {"quality-job": {"state": "pending"}}, {"quality-job": report})

    assert "65 · warn" in detail
    assert "Issues and suggested fixes" in detail
    assert "&lt;script&gt;alert" in detail
    assert "&lt;img src=x" in detail
    assert "<script>alert" not in detail
    assert "65 · warn" in index


def test_mission_control_score_post_updates_detail_and_index_only(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    write_quality_job(output_root)
    server = create_server(output_root, "127.0.0.1", 0, export_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("POST", "/jobs/quality-job/score", body=b"")
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/jobs/quality-job")
        detail = connection.getresponse()
        detail_page = detail.read().decode("utf-8")
        assert detail.status == 200
        assert "Quality score" in detail_page
        assert "Re-score Job" in detail_page
        assert "Quality pass does not approve or export this job." in detail_page
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/")
        index = connection.getresponse()
        index_page = index.read().decode("utf-8")
        assert index.status == 200
        assert "quality-pass" in index_page
        assert QualityStore(output_root).read("quality-job")["status"] == "pass"
        assert not (output_root / "approvals" / "quality-job.json").exists()
        assert not export_root.exists()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
