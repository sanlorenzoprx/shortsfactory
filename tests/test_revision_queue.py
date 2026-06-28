import http.client
import json
import threading
import urllib.parse
from pathlib import Path

import pytest

from content_factory.mission_control.app import create_server
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.revisions.revision_queue import RevisionQueue, RevisionTaskError


def write_minimal_job(output_root: Path, job_id: str = "original-123") -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "receipt.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "created_at": "2026-06-28T17:00:00+00:00",
                "locale": "en-US",
                "mode": "mock",
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    return job_dir


def test_revision_task_can_be_created_and_updated(tmp_path):
    output_root = tmp_path / "output"
    job_dir = write_minimal_job(output_root)
    queue = RevisionQueue(output_root)

    task = queue.create("original-123", "Tighten the hook")
    updated = queue.create("original-123", "Make the CTA clearer")

    assert task["state"] == "revision_queued"
    assert task["attempts"] == 0
    assert task["source_receipt"] == str((job_dir / "receipt.json").resolve())
    assert updated["created_at"] == task["created_at"]
    assert updated["revision_note"] == "Make the CTA clearer"
    assert queue.read("original-123") == updated
    assert (output_root / "revisions" / "original-123.json").is_file()


def test_revision_task_requires_a_note(tmp_path):
    output_root = tmp_path / "output"
    write_minimal_job(output_root)

    with pytest.raises(RevisionTaskError, match="revision note is required"):
        RevisionQueue(output_root).create("original-123", "  ")


@pytest.mark.parametrize("job_id", ["../escape", "..", "nested/job", "nested\\job"])
def test_revision_task_rejects_path_traversal(tmp_path, job_id):
    with pytest.raises(RevisionTaskError, match="invalid job_id"):
        RevisionQueue(tmp_path / "output").task_path(job_id)


def test_mission_control_creates_local_revision_task_and_escapes_note(tmp_path):
    output_root = tmp_path / "output"
    write_minimal_job(output_root)
    server = create_server(output_root, "127.0.0.1", 0, tmp_path / "exports")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    note = "<script>alert('revision')</script> tighten hook"
    body = urllib.parse.urlencode({"revision_note": note}).encode()
    try:
        connection.request(
            "POST",
            "/jobs/original-123/revision-task",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        connection.close()

        task = RevisionQueue(output_root).read("original-123")
        assert task["revision_note"] == note
        assert ApprovalStore(output_root).read("original-123")["state"] == "needs_revision"

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/jobs/original-123")
        detail = connection.getresponse()
        page = detail.read().decode("utf-8")
        assert detail.status == 200
        assert "&lt;script&gt;alert" in page
        assert "<script>alert" not in page
        assert "Run Local Revision" in page
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
