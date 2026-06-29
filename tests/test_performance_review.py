from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from content_factory.results.result_models import SAFETY_FLAGS as RESULT_SAFETY_FLAGS
from performance_review import main as performance_main


def manual_entry(
    entry_id: str,
    *,
    job_id: str = "job-one",
    platform: str = "youtube_shorts",
    created_at: str = "2026-06-28T10:00:00+00:00",
    views: int = 100,
    likes: int = 10,
    comments: int = 2,
    shares: int = 1,
    saves: int = 3,
    leads: int = 1,
    quality_score: int | None = 92,
    template_id: str | None = "script.default",
    notes: str = "Keep the direct hook.",
) -> dict:
    templates = {"script": template_id} if template_id else {}
    return {
        "entry_id": entry_id,
        "created_at": created_at,
        "updated_at": created_at,
        "job_id": job_id,
        "platform": platform,
        "manual_upload_url": f"https://example.com/{entry_id}",
        "manual_upload_date": "2026-06-28",
        "metrics": {
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "leads": leads,
        },
        "context": {
            "quality_score": quality_score,
            "quality_status": "pass" if quality_score is not None else None,
            "compliance_status": "ready_for_manual_upload",
            "template_ids": templates,
            "template_hashes": {},
        },
        "notes": notes,
        "lessons": ["Use the local signal for the next manual test."],
        "source": "manual_entry",
        "safety": dict(RESULT_SAFETY_FLAGS),
    }


def write_entries(results_root: Path, entries: list[dict]) -> None:
    root = results_root / "entries"
    root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        (root / f"{entry['entry_id']}.json").write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8"
        )


def test_performance_cli_help_works(capsys):
    with pytest.raises(SystemExit) as excinfo:
        performance_main(["--help"])
    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "deterministic local performance review" in output
    assert "manually" in output


def test_empty_ledger_writes_clear_empty_state(tmp_path: Path):
    results_root = tmp_path / "missing results"
    output_root = tmp_path / "performance reports"
    assert performance_main(["--results-root", str(results_root), "--output-root", str(output_root)]) == 0
    report = json.loads((output_root / "PERFORMANCE_REVIEW.json").read_text(encoding="utf-8"))
    markdown = (output_root / "PERFORMANCE_REVIEW.md").read_text(encoding="utf-8")
    assert report["status"] == "empty"
    assert report["totals"]["entries"] == 0
    assert "No manual results recorded yet." in markdown
    assert "Record a result with results_ledger.py before reviewing performance." in markdown
    for filename in ("platform_summary.csv", "template_summary.csv", "job_summary.csv"):
        assert (output_root / filename).is_file()


def test_valid_ledger_writes_all_reports_and_safety_flags(tmp_path: Path):
    results_root = tmp_path / "results ledger"
    output_root = tmp_path / "performance reports"
    write_entries(
        results_root,
        [
            manual_entry("entry-one"),
            manual_entry(
                "entry-two",
                job_id="job-two",
                platform="tiktok",
                created_at="2026-06-28T11:00:00+00:00",
                views=300,
                likes=45,
                comments=5,
                shares=4,
                saves=6,
                leads=0,
                quality_score=88,
                template_id="script.alternate",
            ),
        ],
    )
    assert performance_main(["--results-root", str(results_root), "--output-root", str(output_root)]) == 0
    report = json.loads((output_root / "PERFORMANCE_REVIEW.json").read_text(encoding="utf-8"))
    assert report["status"] == "ready"
    assert report["totals"] == {
        "entries": 2, "platforms": 2, "views": 400, "likes": 55,
        "comments": 7, "shares": 5, "saves": 9, "leads": 1,
    }
    assert report["rates"]["like_rate"] == 0.1375
    assert report["quality_summary"] == {
        "average_quality_score": 90,
        "best_quality_score": 92,
        "worst_quality_score": 88,
    }
    assert report["safety"] == {
        "manual_results_only": True,
        "api_fetch_attempted": False,
        "api_upload_attempted": False,
        "scraping_attempted": False,
        "live_publishing_enabled": False,
    }
    assert "not statistically proven" in report["recommendations"][0]["message"]
    with (output_root / "platform_summary.csv").open(encoding="utf-8", newline="") as handle:
        assert {row["platform"] for row in csv.DictReader(handle)} == {"youtube_shorts", "tiktok"}
    with (output_root / "template_summary.csv").open(encoding="utf-8", newline="") as handle:
        assert {row["template_id"] for row in csv.DictReader(handle)} == {"script.default", "script.alternate"}
    with (output_root / "job_summary.csv").open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 2
