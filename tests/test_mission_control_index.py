import json
from pathlib import Path

from content_factory.mission_control.approvals import ApprovalStore
from content_factory.mission_control.job_index import find_job, is_within, scan_jobs
from content_factory.mission_control.templates import DRY_RUN_LABEL, render_job_detail


def write_job(root: Path, relative_dir: str, job_id: str, **receipt_fields) -> Path:
    job_dir = root / relative_dir / job_id
    job_dir.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T12:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "status": "complete",
        "warnings": [],
        **receipt_fields,
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    return job_dir


def test_job_index_finds_both_phase_3a_job_roots(tmp_path):
    first = write_job(tmp_path, "jobs", "job-one", source="mock")
    second = write_job(tmp_path, "phase2g-acceptance/jobs", "job-two")
    (first / "short.mp4").write_bytes(b"video")
    (second / "publish").mkdir()
    (second / "publish" / "publisher_plan.json").write_text("{}", encoding="utf-8")

    jobs = scan_jobs(tmp_path)

    assert {job.job_id for job in jobs} == {"job-one", "job-two"}
    assert find_job(tmp_path, "job-one").artifacts["short.mp4"] == (first / "short.mp4").resolve()
    assert "publisher_package.json" in find_job(tmp_path, "job-two").artifacts


def test_missing_optional_artifacts_do_not_break_detail_page(tmp_path):
    write_job(tmp_path, "jobs", "minimal-job")
    job = find_job(tmp_path, "minimal-job")

    page = render_job_detail(job, ApprovalStore.pending(job.job_id))

    assert "No generated MP4 available" in page
    assert "No thumbnail available" in page
    assert "Not available" in page
    assert DRY_RUN_LABEL in page


def test_script_captions_and_json_are_html_escaped(tmp_path):
    job_dir = write_job(
        tmp_path,
        "jobs",
        "unsafe-copy",
        warnings=["<img src=x onerror=alert(1)>"],
    )
    (job_dir / "script.txt").write_text("<script>alert('script')</script>", encoding="utf-8")
    (job_dir / "captions.srt").write_text("<b>caption</b>", encoding="utf-8")

    page = render_job_detail(find_job(tmp_path, "unsafe-copy"), ApprovalStore.pending("unsafe-copy"))

    assert "<script>alert" not in page
    assert "<b>caption</b>" not in page
    assert "&lt;script&gt;alert" in page
    assert "&lt;b&gt;caption&lt;/b&gt;" in page
    assert "<img src=x" not in page


def test_unlisted_roots_and_outside_paths_are_ignored(tmp_path):
    write_job(tmp_path, "other/jobs", "not-indexed")

    assert scan_jobs(tmp_path) == []
    assert not is_within(tmp_path.parent / "outside.txt", tmp_path)
