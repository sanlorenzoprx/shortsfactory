from pathlib import Path

import pytest

from content_factory.quality.quality_store import QualityStore, QualityStoreError


def report(job_id: str = "quality-123", score: int = 84) -> dict:
    return {
        "job_id": job_id,
        "scored_at": "2026-06-28T18:00:00+00:00",
        "overall_score": score,
        "status": "pass",
        "approval_ready": True,
        "export_ready": False,
        "recommended_action": "approve",
        "category_scores": {},
        "issues": [],
        "missing_artifacts": [],
        "present_artifacts": [],
        "checks": {},
        "scoring_version": "phase3d.v1",
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
    }


def test_quality_store_writes_reads_and_replaces_same_report(tmp_path):
    store = QualityStore(tmp_path / "output")
    first = report(score=84)
    second = report(score=91)

    path = store.write(first)
    second_path = store.write(second)

    assert path == second_path == (tmp_path / "output" / "quality" / "quality-123.json").resolve()
    assert store.read("quality-123") == second


@pytest.mark.parametrize("job_id", ["../escape", "..", "nested/job", "nested\\job"])
def test_quality_store_rejects_path_traversal(tmp_path, job_id):
    with pytest.raises(QualityStoreError, match="invalid job_id"):
        QualityStore(tmp_path / "output").report_path(job_id)


def test_quality_store_rejects_live_publishing_report(tmp_path):
    unsafe = report()
    unsafe["live_publishing_enabled"] = True

    with pytest.raises(QualityStoreError, match="safety validation"):
        QualityStore(tmp_path / "output").write(unsafe)
