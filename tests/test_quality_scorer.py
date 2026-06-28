import json
from pathlib import Path

import pytest

from content_factory.exporting.bundle_exporter import BundleExportError, export_approved_bundle
from content_factory.quality.quality_scorer import QualityScoringError, score_job
from content_factory.quality.quality_store import QualityStore


def write_quality_job(
    output_root: Path,
    job_id: str = "quality-job",
    locale: str = "en-US",
    script: str | None = None,
) -> Path:
    job_dir = output_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    if script is None:
        script = (
            "Test this idea before you build: Local Bakery App.\n"
            "Score: 82/100.\n"
            "Main risk: medium.\n"
            "The outcome is promising if customer acquisition is tested.\n"
            "Verdict: test the idea.\n"
            "Test this idea now, then decide what to build.\n"
        )
    idea = {
        "name": "Local Bakery App",
        "description": "Ordering tools for local bakeries.",
        "target_user": "bakery owners",
        "market": "US",
    }
    verdict = {
        "idea": idea,
        "verdict_headline": "Test the idea",
        "lit_score": 82,
        "risk_level": "medium",
        "top_reason": "Customer acquisition needs testing.",
        "next_step": "Test with three bakeries.",
        "source": "mock",
    }
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T18:05:00+00:00",
        "locale": locale,
        "mode": "mock",
        "idea": idea,
        "verdict": verdict,
        "outputs": {},
        "warnings": [],
        "recording": {"enabled": False},
        "voiceover": {"status": "disabled"},
        "music": {"status": "disabled"},
        "publisher": {"status": "disabled"},
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (job_dir / "script.txt").write_text(script, encoding="utf-8")
    captions = f"1\n00:00:00,000 --> 00:00:30,000\n{script}\n"
    (job_dir / "captions.srt").write_text(captions, encoding="utf-8")
    (job_dir / "thumbnail.jpg").write_bytes(b"jpeg")
    (job_dir / "short.mp4").write_bytes(b"video")
    return job_dir


def issues_for(report: dict, category: str) -> list[dict]:
    return [item for item in report["issues"] if item["category"] == category]


def test_quality_score_writes_safe_report_without_approval_or_export(tmp_path):
    output_root = tmp_path / "output"
    write_quality_job(output_root)

    report = score_job("quality-job", output_root)

    path = output_root / "quality" / "quality-job.json"
    assert path.is_file()
    assert report["status"] == "pass"
    assert report["overall_score"] >= 80
    assert report["approval_ready"] is True
    assert report["export_ready"] is False
    assert report["recommended_action"] == "approve"
    assert report["publishing_status"] == "not_published"
    assert report["live_publishing_enabled"] is False
    assert report["checks"]["has_receipt"] is True
    assert report["checks"]["has_approval"] is False
    assert not (output_root / "approvals" / "quality-job.json").exists()
    assert not (tmp_path / "exports").exists()
    with pytest.raises(BundleExportError, match="approval record is missing"):
        export_approved_bundle("quality-job", output_root, tmp_path / "exports")


def test_scorer_refuses_missing_job_and_path_traversal(tmp_path):
    with pytest.raises(QualityScoringError, match="job not found"):
        score_job("missing-job", tmp_path / "output")
    with pytest.raises(QualityScoringError, match="invalid job_id"):
        score_job("../escape", tmp_path / "output")


def test_scorer_handles_missing_optional_assets(tmp_path):
    output_root = tmp_path / "output"
    job_dir = write_quality_job(output_root)
    (job_dir / "captions.srt").unlink()
    (job_dir / "thumbnail.jpg").unlink()

    report = score_job("quality-job", output_root)

    assert "captions.srt" in report["missing_artifacts"]
    assert "thumbnail.jpg" in report["missing_artifacts"]
    assert report["category_scores"]["captions"] == 0
    assert issues_for(report, "captions")
    assert issues_for(report, "media")


def test_scorer_fails_when_no_mp4_exists(tmp_path):
    output_root = tmp_path / "output"
    job_dir = write_quality_job(output_root)
    (job_dir / "short.mp4").unlink()

    report = score_job("quality-job", output_root)

    assert report["status"] == "fail"
    assert report["checks"]["has_video"] is False
    assert "video.mp4" in report["missing_artifacts"]
    assert any(item["severity"] == "error" for item in issues_for(report, "media"))


def test_scorer_detects_invalid_receipt_and_script_placeholders(tmp_path):
    output_root = tmp_path / "output"
    job_dir = write_quality_job(
        output_root,
        script="Welcome to this video.\nTODO: {{headline}}\nSomething happens.\nLearn more.",
    )
    (job_dir / "receipt.json").write_text("{not valid json", encoding="utf-8")

    report = score_job("quality-job", output_root)

    assert report["status"] == "fail"
    assert report["checks"]["has_receipt"] is False
    assert any(item["severity"] == "error" for item in issues_for(report, "receipt"))
    assert any("placeholder" in item["message"].lower() for item in issues_for(report, "clarity"))


def test_scorer_detects_caption_timestamps_and_weak_cta(tmp_path):
    output_root = tmp_path / "output"
    script = "Test this score before building.\nScore: 70.\nRisk: medium.\nMaybe someday."
    write_quality_job(output_root, script=script)

    report = score_job("quality-job", output_root)

    assert report["category_scores"]["captions"] == 100
    assert report["category_scores"]["cta"] < 60
    assert issues_for(report, "cta")


def test_scorer_recognizes_es_pr_localization(tmp_path):
    output_root = tmp_path / "output"
    script = (
        "Prueba esta idea antes de construir.\n"
        "Puntuación: 82/100.\n"
        "Riesgo: medio.\n"
        "Veredicto: prueba con clientes.\n"
        "Prueba esta idea ahora.\n"
    )
    write_quality_job(output_root, locale="es-PR", script=script)

    report = score_job("quality-job", output_root)

    assert report["category_scores"]["localization"] == 100


def test_rescoring_replaces_same_report_with_same_deterministic_scores(tmp_path):
    output_root = tmp_path / "output"
    write_quality_job(output_root)

    first = score_job("quality-job", output_root)
    second = score_job("quality-job", output_root)

    assert first["overall_score"] == second["overall_score"]
    assert first["category_scores"] == second["category_scores"]
    assert QualityStore(output_root).read("quality-job") == second
    assert list((output_root / "quality").glob("quality-job*.json")) == [
        output_root / "quality" / "quality-job.json"
    ]
