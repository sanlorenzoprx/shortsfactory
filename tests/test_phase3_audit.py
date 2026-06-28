from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_factory.audits.phase3_audit import AUDIT_JOB_ID, Phase3AuditError, run_phase3_audit
from content_factory.revisions.revision_queue import RevisionQueue


def _write_job(output_root: Path, job_id: str, *, revised: bool = False) -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    idea = {"name": "Audit idea", "description": "A local audit fixture", "target_user": "builders", "market": "US"}
    verdict = {"idea": idea, "verdict_headline": "Promising if tested", "lit_score": 78, "risk_level": "medium", "top_reason": "Demand needs proof.", "next_step": "Test it with builders.", "source": "mock"}
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T20:00:00+00:00",
        "locale": "en-US",
        "mode": "revision" if revised else "mock",
        "idea": idea,
        "verdict": verdict,
        "outputs": {},
        "warnings": [],
        "recording": {"enabled": False},
        "voiceover": {"status": "disabled"},
        "music": {"status": "disabled"},
        "publisher": {"status": "disabled"},
    }
    if revised:
        receipt["revision"] = {"is_revision": True, "original_job_id": AUDIT_JOB_ID, "revision_note": "Audit revision", "requires_reapproval": True}
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (job_dir / "script.txt").write_text("Test this audit idea before you build.\nScore: 78/100.\nMain risk: medium.\nDemand needs proof.\nVerdict: Promising if tested.\nTest it now before you build.\n", encoding="utf-8")
    (job_dir / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:05,000\nTest this audit idea before you build.\n", encoding="utf-8")
    (job_dir / "thumbnail.jpg").write_bytes(b"tiny-jpeg")
    (job_dir / "short.mp4").write_bytes(b"tiny-mp4")
    return job_dir


def _fixture_pair(output_root: Path) -> str:
    original = _write_job(output_root, AUDIT_JOB_ID)
    revised_id = f"{AUDIT_JOB_ID}-rfixture"
    revised = _write_job(output_root, revised_id, revised=True)
    manifest = {
        "original_job_id": AUDIT_JOB_ID,
        "revised_job_id": revised_id,
        "requires_reapproval": True,
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
    }
    (revised / "REVISION_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    RevisionQueue(output_root).write(
        {
            "job_id": AUDIT_JOB_ID,
            "state": "revision_complete",
            "created_at": "2026-06-28T20:01:00+00:00",
            "updated_at": "2026-06-28T20:01:00+00:00",
            "revision_note": "Audit revision",
            "requested_by": "local_user",
            "source_receipt": str(original / "receipt.json"),
            "revised_job_id": revised_id,
            "attempts": 1,
            "warnings": [],
        }
    )
    return revised_id


def test_phase3_audit_creates_complete_safe_demo_dataset(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    demo_root = tmp_path / "demo_dataset"
    revised_id = _fixture_pair(output_root)

    result = run_phase3_audit(
        output_root,
        export_root,
        demo_root,
        template_root=tmp_path / "templates",
        report_path=tmp_path / "docs" / "audits" / "PHASE_3_LOCAL_OS_AUDIT.md",
    )

    receipt = json.loads((demo_root / "audit_receipt.json").read_text(encoding="utf-8"))
    assert result.revised_job_id == revised_id
    assert receipt["status"] == "pass"
    assert all(receipt["flow_verified"].values())
    assert receipt["safety"]["live_publishing_enabled"] is False
    assert receipt["safety"]["api_upload_attempted"] is False
    assert receipt["safety"]["manual_upload_only"] is True
    required = [
        "demo_jobs/original/receipt.json",
        "demo_jobs/revised/REVISION_MANIFEST.json",
        "demo_quality/original_quality.json",
        "demo_quality/revised_quality.json",
        "demo_exports/approved/EXPORT_MANIFEST.json",
        "demo_upload_kits/UPLOAD_KIT_MANIFEST.json",
        "demo_upload_kits/youtube_shorts/platform_metadata.json",
        "demo_upload_kits/tiktok/platform_metadata.json",
        "demo_upload_kits/instagram_reels/platform_metadata.json",
        "demo_templates/template_validation.json",
        "demo_templates/script_default_preview.txt",
    ]
    assert all((demo_root / relative).is_file() for relative in required)
    media = json.loads((demo_root / "demo_jobs" / "original" / "media_manifest.json").read_text(encoding="utf-8"))
    assert media["copy_media_enabled"] is False
    assert media["media_files_detected"]
    assert not any(item["copied"] for item in media["media_files_detected"])
    assert not (demo_root / "demo_jobs" / "original" / "short.mp4").exists()
    assert result.report_path.is_file()


def test_phase3_audit_rejects_demo_path_traversal(tmp_path: Path):
    with pytest.raises(Phase3AuditError, match="path traversal"):
        run_phase3_audit(tmp_path / "output", tmp_path / "exports", "../escape")
