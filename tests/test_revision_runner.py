import hashlib
import json
from pathlib import Path

import pytest

from content_factory.exporting.bundle_exporter import BundleExportError, export_approved_bundle
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.mission_control.job_index import find_job
from content_factory.mission_control.templates import render_job_detail
from content_factory.revisions.revision_queue import RevisionQueue
from content_factory.revisions.revision_runner import (
    RevisionRunError,
    revise_script,
    run_revision,
)
from content_factory.schemas import ShortScript


def write_revision_source(output_root: Path, job_id: str = "original-456") -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    idea = {
        "name": "Local Bakery App",
        "description": "Local ordering for neighborhood bakeries.",
        "target_user": "bakery owners",
        "market": "US",
    }
    verdict = {
        "idea": idea,
        "verdict_headline": "Promising if tested",
        "lit_score": 72,
        "risk_level": "medium",
        "top_reason": "Demand is plausible, but the acquisition path needs testing.",
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
    (job_dir / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    (job_dir / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    (job_dir / "script.txt").write_text(
        "I ran this bakery idea through the test.\n"
        "Score: 72/100.\n"
        "Main risk: medium.\n"
        "Demand is plausible, but the acquisition path needs testing.\n"
        "Verdict: Promising if tested.\n"
        "Do not build blind. Test your idea first.\n",
        encoding="utf-8",
    )
    (job_dir / "short.mp4").write_bytes(b"original-placeholder-video")
    return job_dir


def file_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_revision_refuses_missing_task_without_note(tmp_path):
    output_root = tmp_path / "output"
    write_revision_source(output_root)
    ApprovalStore(output_root).write("original-456", "needs_revision", "Tighten hook")

    with pytest.raises(RevisionRunError, match="revision task is missing"):
        run_revision("original-456", output_root)


def test_revision_requires_needs_revision_approval_state(tmp_path):
    output_root = tmp_path / "output"
    write_revision_source(output_root)
    RevisionQueue(output_root).create("original-456", "Tighten hook")

    with pytest.raises(RevisionRunError, match="must be marked needs_revision"):
        run_revision("original-456", output_root)


def test_revision_creates_linked_job_requiring_separate_approval(tmp_path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    source_dir = write_revision_source(output_root)
    original_hashes = file_hashes(source_dir)
    note = "Tighten hook and CTA, make it shorter"
    ApprovalStore(output_root).write("original-456", "needs_revision", note)
    RevisionQueue(output_root).create("original-456", note)

    result = run_revision("original-456", output_root)

    assert result.revised_job_id != "original-456"
    assert result.revised_job_dir == output_root.resolve() / "jobs" / result.revised_job_id
    assert file_hashes(source_dir) == original_hashes
    required = {
        "script.txt",
        "captions.srt",
        "thumbnail.jpg",
        "short.mp4",
        "receipt.json",
        "REVISION_MANIFEST.json",
    }
    assert required.issubset({path.name for path in result.revised_job_dir.iterdir()})

    manifest = json.loads(
        (result.revised_job_dir / "REVISION_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["original_job_id"] == "original-456"
    assert manifest["revised_job_id"] == result.revised_job_id
    assert manifest["requires_reapproval"] is True
    assert manifest["publishing_status"] == "not_published"
    assert manifest["live_publishing_enabled"] is False

    receipt = json.loads((result.revised_job_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["revision"] == {
        "is_revision": True,
        "original_job_id": "original-456",
        "revision_note": note,
        "revision_strategy": "deterministic_local_rules",
        "requires_reapproval": True,
    }
    assert receipt["publisher"]["status"] == "disabled"
    assert ApprovalStore(output_root).read(result.revised_job_id)["state"] == "pending"
    assert not (output_root / "approvals" / f"{result.revised_job_id}.json").exists()

    script = (result.revised_job_dir / "script.txt").read_text(encoding="utf-8")
    assert script.startswith("Test this before you build: Local Bakery App.")
    assert "Test this idea now, then decide what to build." in script
    task = RevisionQueue(output_root).read("original-456")
    assert task["state"] == "revision_complete"
    assert task["revised_job_id"] == result.revised_job_id
    assert task["attempts"] == 1

    with pytest.raises(BundleExportError, match="approval record is missing"):
        export_approved_bundle(result.revised_job_id, output_root, export_root)

    ApprovalStore(output_root).write(result.revised_job_id, "approved", "Reapproved revision")
    exported = export_approved_bundle(result.revised_job_id, output_root, export_root)
    assert exported.manifest["publishing_status"] == "not_published"
    assert exported.manifest["live_publishing_enabled"] is False

    revised_job = find_job(output_root, result.revised_job_id)
    detail = render_job_detail(
        revised_job,
        {"state": "pending"},
        revision_manifest=manifest,
    )
    assert 'href="/jobs/original-456"' in detail
    assert "Requires reapproval" in detail


def test_unrecognized_revision_note_is_preserved_as_safe_focus():
    original = ShortScript(
        hook="Original hook",
        body_lines=["Original body"],
        verdict_reveal="Original verdict",
        cta="Original CTA",
    )

    revised = revise_script(original, "Use more concrete proof", "Idea", "en-US")

    assert revised.body_lines[-1] == "Revision focus: Use more concrete proof"


@pytest.mark.parametrize("job_id", ["../escape", "nested/job"])
def test_revision_runner_rejects_path_traversal(tmp_path, job_id):
    with pytest.raises(RevisionRunError, match="invalid job_id"):
        run_revision(job_id, tmp_path / "output")
