from __future__ import annotations

import hashlib
import http.client
import json
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.revisions.revision_queue import RevisionQueue


def _write_source(output_root: Path, job_id: str = "route-job") -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    idea = {
        "name": "Local Bakery App",
        "description": "Ordering for neighborhood bakeries.",
        "target_user": "bakery owners",
        "market": "US",
    }
    verdict = {
        "idea": idea,
        "verdict_headline": "Promising if tested",
        "lit_score": 72,
        "risk_level": "medium",
        "top_reason": "Demand needs proof.",
        "next_step": "Test with three bakeries.",
        "source": "mock",
    }
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T17:10:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": idea,
        "verdict": verdict,
        "outputs": {},
        "warnings": [],
        "localization": {"resolved_locale": "en-US", "warnings": []},
    }
    (job_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    (job_dir / "verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    (job_dir / "script.txt").write_text(
        "Original hook.\nScore: 72/100.\nMain risk: medium.\n"
        "Demand needs proof.\nVerdict: Promising if tested.\nOriginal CTA.\n",
        encoding="utf-8",
    )
    (job_dir / "short.mp4").write_bytes(b"original-video")
    return job_dir


def _hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _post(server, path: str) -> tuple[int, str | None, str]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=30
    )
    try:
        connection.request("POST", path, body=b"")
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("Location"),
            response.read().decode("utf-8"),
        )
    finally:
        connection.close()


def test_run_revision_route_supports_space_paths_and_redirects_to_revised_job(
    tmp_path: Path,
):
    output_root = tmp_path / "Shorts Factory output"
    source_dir = _write_source(output_root)
    before = _hashes(source_dir)
    note = "Tighten hook and CTA"
    ApprovalStore(output_root).write("route-job", "needs_revision", note)
    RevisionQueue(output_root).create("route-job", note)
    server = create_server(
        output_root,
        "127.0.0.1",
        0,
        tmp_path / "exports with spaces",
        tmp_path / "templates with spaces",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, location, _ = _post(server, "/jobs/route-job/run-revision")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 303
    assert location is not None and location.startswith("/jobs/route-job-r")
    revised_job_id = location.removeprefix("/jobs/")
    revised_dir = output_root / "jobs" / revised_job_id
    assert (revised_dir / "REVISION_MANIFEST.json").is_file()
    assert _hashes(source_dir) == before
    receipt = json.loads((revised_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["revision"]["requires_reapproval"] is True
    assert ApprovalStore(output_root).read(revised_job_id)["state"] == "pending"
    assert not (output_root / "approvals" / f"{revised_job_id}.json").exists()


def test_run_revision_route_returns_safe_error_page(tmp_path: Path):
    output_root = tmp_path / "output with spaces"
    _write_source(output_root, "not-ready")
    server = create_server(output_root, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, location, body = _post(server, "/jobs/not-ready/run-revision")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 409
    assert location is None
    assert "must be marked needs_revision" in body
    assert "Traceback" not in body
