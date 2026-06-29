from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

from content_factory.compliance import mark_compliance_reviewed
from content_factory.mission_control.app import create_server
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.results import ResultsLedgerStore
from tests.test_compliance_check import create_compliance_sources, write_json
from tests.test_results_ledger import quality_report
from content_factory.quality.quality_store import QualityStore


def create_job(output_root: Path, export_root: Path, job_id: str = "results-job", *, ready: bool = True) -> None:
    job = output_root / "jobs" / job_id
    job.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T20:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": {"name": "Results"},
        "verdict": {"verdict_headline": "Review safely"},
        "outputs": {},
        "warnings": [],
        "templates": {
            "script": {"template_id": "script.default", "template_version_hash": "sha256:script", "source": "local_template"},
            "caption": {"template_id": "caption.default", "template_version_hash": "sha256:caption", "source": "local_template"},
            "thumbnail": {"template_id": "thumbnail.default", "template_version_hash": "sha256:thumbnail", "source": "local_template"},
        },
    }
    write_json(job / "receipt.json", receipt)
    (job / "script.txt").write_text("Results test.", encoding="utf-8")
    (job / "short.mp4").write_bytes(b"video")
    ApprovalStore(output_root).write(job_id, "approved", "Approved for results")
    create_compliance_sources(export_root, job_id=job_id)
    write_json(export_root / "approved" / job_id / "receipt.json", receipt)
    QualityStore(output_root).write(quality_report(job_id))
    if ready:
        mark_compliance_reviewed(job_id, export_root)


def request(server, method: str, path: str, body: bytes = b"") -> tuple[int, str, str | None]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if method == "POST" else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), response.getheader("Location")
    finally:
        connection.close()


def test_mission_control_hides_results_form_until_compliance_ready(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_job(output_root, export_root, ready=False)
    server = create_server(output_root, "127.0.0.1", 0, export_root, tmp_path / "templates", tmp_path / "results")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, page, _ = request(server, "GET", "/jobs/results-job")
        assert status == 200
        assert "Results Ledger unavailable until compliance is Ready for Manual Upload." in page
        assert "Record Manual Result" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_mission_control_records_and_updates_manual_results(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    results_root = tmp_path / "results_ledger"
    create_job(output_root, export_root, ready=True)
    server = create_server(output_root, "127.0.0.1", 0, export_root, tmp_path / "templates", results_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, before, _ = request(server, "GET", "/jobs/results-job")
        assert status == 200
        assert "Record Manual Result" in before
        assert "Open Results Summary" in before
        assert "Fetch Metrics" not in before
        assert "Sync YouTube" not in before
        assert "OAuth" not in before
        body = (
            "platform=youtube_shorts&url=https%3A%2F%2Fexample.com%2Fmanual-upload"
            "&views=100&likes=10&comments=1&shares=2&saves=0&leads=0&notes=Manual+upload+test"
        ).encode("utf-8")
        status, _, location = request(server, "POST", "/jobs/results-job/results", body=body)
        assert status == 303
        assert location == "/jobs/results-job"
        status, after, _ = request(server, "GET", "/jobs/results-job")
        assert status == 200
        assert "Update Manual Result" in after
        assert "https://example.com/manual-upload" in after
        assert ">Publish<" not in after
        assert ">Post<" not in after
        assert "Upload automatically" not in after
        assert "Connect account" not in after
        entry_id = ResultsLedgerStore(results_root, export_root=export_root, output_root=output_root).list_entries()[0]["entry_id"]
        assert entry_id
        status, summary, _ = request(server, "GET", "/results/summary")
        assert status == 200
        assert "Manual Results Summary" in summary
        status, entry_json, _ = request(server, "GET", f"/results/entries/{entry_id}")
        assert status == 200
        entry = json.loads(entry_json)
        assert entry["metrics"]["views"] == 100
        assert entry["safety"]["api_fetch_attempted"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
