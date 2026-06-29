from __future__ import annotations

import json
from pathlib import Path

import pytest

from compliance_check import main as compliance_main
from content_factory.compliance import mark_compliance_reviewed
from content_factory.quality.quality_store import QualityStore
from content_factory.results import ResultsLedgerError, ResultsLedgerStore
from results_ledger import main as results_main
from tests.test_compliance_check import create_compliance_sources, write_json


def quality_report(job_id: str, score: int = 92) -> dict:
    return {
        "job_id": job_id,
        "scored_at": "2026-06-28T18:00:00+00:00",
        "overall_score": score,
        "status": "pass",
        "approval_ready": True,
        "export_ready": True,
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


def create_ready_result_sources(
    output_root: Path,
    export_root: Path,
    job_id: str = "ready-job",
) -> None:
    job = output_root / "jobs" / job_id
    job.mkdir(parents=True)
    receipt = {
        "job_id": job_id,
        "created_at": "2026-06-28T20:00:00+00:00",
        "locale": "en-US",
        "mode": "mock",
        "idea": {"name": "Results"},
        "verdict": {"verdict_headline": "Manual results"},
        "outputs": {},
        "warnings": [],
        "templates": {
            "script": {
                "template_id": "script.default",
                "template_version_hash": "sha256:script",
                "source": "local_template",
            },
            "caption": {
                "template_id": "caption.default",
                "template_version_hash": "sha256:caption",
                "source": "local_template",
            },
            "thumbnail": {
                "template_id": "thumbnail.default",
                "template_version_hash": "sha256:thumbnail",
                "source": "local_template",
            },
        },
    }
    write_json(job / "receipt.json", receipt)
    (job / "script.txt").write_text("Manual result test.", encoding="utf-8")
    (job / "short.mp4").write_bytes(b"video")
    create_compliance_sources(export_root, job_id=job_id)
    write_json(export_root / "approved" / job_id / "receipt.json", receipt)
    QualityStore(output_root).write(quality_report(job_id))
    mark_compliance_reviewed(job_id, export_root)


def test_results_cli_help_works(capsys):
    with pytest.raises(SystemExit) as excinfo:
        results_main(["--help"])
    assert excinfo.value.code == 0
    assert "manual upload results" in capsys.readouterr().out


def test_results_require_ready_compliance(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root, job_id="blocked-job")
    with pytest.raises(ResultsLedgerError, match="Run compliance_check.py and mark reviewed"):
        ResultsLedgerStore(tmp_path / "results", export_root=export_root, output_root=output_root).record_result(
            job_id="blocked-job",
            platform="youtube_shorts",
            manual_upload_url="https://example.com/manual-upload",
        )


def test_results_reject_missing_upload_kit_and_preview_manifest(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_ready_result_sources(output_root, export_root, job_id="ready-job")
    for path in sorted((export_root / "upload_kits" / "ready-job").rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    (export_root / "upload_kits" / "ready-job").rmdir()
    with pytest.raises(ResultsLedgerError, match="manual upload kit is missing"):
        ResultsLedgerStore(tmp_path / "results", export_root=export_root, output_root=output_root).record_result(
            job_id="ready-job",
            platform="youtube_shorts",
            manual_upload_url="https://example.com/manual-upload",
        )


def test_results_reject_unsafe_url_and_negative_metrics(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_ready_result_sources(output_root, export_root)
    store = ResultsLedgerStore(tmp_path / "results", export_root=export_root, output_root=output_root)
    with pytest.raises(ResultsLedgerError, match="https://"):
        store.record_result(job_id="ready-job", platform="youtube_shorts", manual_upload_url="javascript:alert(1)")
    with pytest.raises(ResultsLedgerError, match="non-negative integer"):
        store.record_result(
            job_id="ready-job",
            platform="youtube_shorts",
            manual_upload_url="https://example.com/manual-upload",
            metrics={"views": -1},
        )


def test_results_record_entry_defaults_missing_metrics_and_captures_context(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    ledger_root = tmp_path / "results_ledger"
    create_ready_result_sources(output_root, export_root)
    store = ResultsLedgerStore(ledger_root, export_root=export_root, output_root=output_root)

    result = store.record_result(
        job_id="ready-job",
        platform="youtube_shorts",
        manual_upload_url="https://example.com/manual-upload",
        metrics={"views": 100, "likes": 10},
        notes="Manual upload test",
    )

    entry = result.entry
    assert entry["metrics"]["views"] == 100
    assert entry["metrics"]["likes"] == 10
    assert entry["metrics"]["comments"] == 0
    assert entry["context"]["quality_score"] == 92
    assert entry["context"]["quality_status"] == "pass"
    assert entry["context"]["compliance_status"] == "ready_for_manual_upload"
    assert entry["context"]["template_ids"]["script"] == "script.default"
    assert entry["context"]["template_hashes"]["script"] == "sha256:script"
    assert entry["safety"] == {
        "manual_upload_only": True,
        "api_fetch_attempted": False,
        "api_upload_attempted": False,
        "scraping_attempted": False,
        "live_publishing_enabled": False,
    }
    assert (ledger_root / "ledger.json").is_file()
    assert (ledger_root / "entries" / f"{entry['entry_id']}.json").is_file()
    assert (ledger_root / "reports" / "RESULTS_SUMMARY.md").is_file()


def test_results_cli_list_show_summary_and_update_work(tmp_path: Path, capsys):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    ledger_root = tmp_path / "results_ledger"
    create_ready_result_sources(output_root, export_root)

    assert results_main(
        [
            "--ledger-root",
            str(ledger_root),
            "--export-root",
            str(export_root),
            "--output-root",
            str(output_root),
            "--job-id",
            "ready-job",
            "--platform",
            "youtube_shorts",
            "--url",
            "https://example.com/manual-upload",
            "--views",
            "100",
            "--likes",
            "10",
            "--notes",
            "Manual upload test",
        ]
    ) == 0
    created_output = capsys.readouterr().out
    assert "Results entry recorded:" in created_output
    entry_id = created_output.split("Results entry recorded: ", 1)[1].splitlines()[0].strip()

    assert results_main(["--ledger-root", str(ledger_root), "--list"]) == 0
    assert entry_id in capsys.readouterr().out

    assert results_main(["--ledger-root", str(ledger_root), "--show", entry_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["entry_id"] == entry_id

    assert results_main(["--ledger-root", str(ledger_root), "--summary"]) == 0
    assert "Manual Results Summary" in capsys.readouterr().out

    assert results_main(
        [
            "--ledger-root",
            str(ledger_root),
            "--update",
            entry_id,
            "--views",
            "250",
            "--likes",
            "25",
            "--notes",
            "Updated after 24 hours",
        ]
    ) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["metrics"]["views"] == 250
    assert updated["notes"] == "Updated after 24 hours"
