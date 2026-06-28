from content_factory.audits.audit_report import FLOW, render_audit_report


def test_audit_report_contains_flow_evidence_and_safety_sections():
    receipt = {
        "status": "pass",
        "repo_commit": "abc123",
        "jobs": {"original_job_id": "original", "revised_job_id": "revised"},
    }
    evidence = {
        "original_receipt": "demo/original/receipt.json",
        "original_media_manifest": "demo/original/media_manifest.json",
        "original_quality": "demo/original_quality.json",
        "original_score": 90,
        "original_status": "pass",
        "revision_task": "output/revisions/original.json",
        "revision_manifest": "demo/revised/REVISION_MANIFEST.json",
        "revised_quality": "demo/revised_quality.json",
        "revised_score": 95,
        "revised_status": "pass",
        "approval": "demo/APPROVAL.json",
        "export_manifest": "demo/EXPORT_MANIFEST.json",
        "upload_kit_manifest": "demo/UPLOAD_KIT_MANIFEST.json",
        "template_validation": "demo/template_validation.json",
        "template_preview": "demo/preview.txt",
        "template_hash": "sha256:abc",
    }

    report = render_audit_report(receipt, evidence)

    assert "# Phase 3 Local OS Audit" in report
    assert FLOW in report
    for heading in ("### 1. Generate", "### 2. Score", "### 3. Review", "### 4. Revise", "### 5. Re-score", "### 6. Approve", "### 7. Export", "### 8. Manual Upload Kit", "### 9. Template Control"):
        assert heading in report
    assert "## Safety Verification" in report
    assert "No live publishing" in report
    assert "No OAuth" in report
    assert "No platform API" in report
