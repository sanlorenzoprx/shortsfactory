from __future__ import annotations

from content_factory.results.result_report import render_results_summary
from content_factory.results.result_summary import best_performing_jobs, ledger_totals, template_signals


def sample_entry(entry_id: str, job_id: str, platform: str, views: int, likes: int, leads: int, template: str) -> dict:
    return {
        "entry_id": entry_id,
        "job_id": job_id,
        "platform": platform,
        "manual_upload_url": "https://example.com/manual-upload",
        "manual_upload_date": "2026-06-28",
        "metrics": {
            "views": views,
            "likes": likes,
            "comments": 1,
            "shares": 2,
            "saves": 0,
            "leads": leads,
        },
        "context": {
            "template_ids": {"script": template},
            "template_hashes": {"script": "sha256:test"},
        },
        "notes": f"Note for {entry_id}",
        "safety": {
            "manual_upload_only": True,
            "api_fetch_attempted": False,
            "api_upload_attempted": False,
            "scraping_attempted": False,
            "live_publishing_enabled": False,
        },
        "created_at": "2026-06-28T20:00:00+00:00",
        "updated_at": "2026-06-28T20:00:00+00:00",
    }


def test_results_summary_helpers_and_markdown():
    entries = [
        sample_entry("entry-1", "job-1", "youtube_shorts", 100, 10, 2, "script.default"),
        sample_entry("entry-2", "job-2", "tiktok", 50, 5, 1, "script.default"),
        sample_entry("entry-3", "job-3", "instagram_reels", 200, 20, 0, "script.alt"),
    ]
    totals = ledger_totals(entries)
    assert totals["entries"] == 3
    assert totals["views"] == 350
    assert best_performing_jobs(entries)[0]["job_id"] == "job-3"
    signals = template_signals(entries)
    assert signals[0]["template"] in {"script.default", "script.alt"}

    markdown = render_results_summary(entries)
    assert "# Manual Results Summary" in markdown
    assert "No platform APIs were called." in markdown
    assert "| Job ID | Platform | Views | Likes | Leads | URL |" in markdown
    assert "| Template | Jobs | Views | Leads |" in markdown
    assert "Note for entry-1" in markdown
