from __future__ import annotations

from typing import Any

from .result_summary import best_performing_jobs, ledger_totals, template_signals


def render_results_summary(entries: list[dict[str, Any]]) -> str:
    totals = ledger_totals(entries)
    best_rows = []
    for entry in best_performing_jobs(entries):
        metrics = entry.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        best_rows.append(
            f"| {entry.get('job_id', '')} | {entry.get('platform', '')} | {metrics.get('views', 0)} | {metrics.get('likes', 0)} | {metrics.get('leads', 0)} | {entry.get('manual_upload_url', '')} |"
        )
    if not best_rows:
        best_rows.append("| None | None | 0 | 0 | 0 |  |")

    template_rows = []
    for row in template_signals(entries):
        template_rows.append(
            f"| {row['template']} | {row['jobs']} | {row['views']} | {row['leads']} |"
        )
    if not template_rows:
        template_rows.append("| None | 0 | 0 | 0 |")

    notes = []
    for entry in entries:
        note = str(entry.get("notes", "")).strip()
        if note:
            notes.append(f"- {entry.get('entry_id', '')}: {note}")
    notes_block = "\n".join(notes) if notes else "- None"

    return f"""# Manual Results Summary

## Safety Boundary

All results are manually entered.
No platform APIs were called.
No scraping was attempted.
Shorts Factory did not publish these videos.

## Totals

- Entries: {totals['entries']}
- Platforms: {', '.join(totals['platforms']) or 'None'}
- Total views: {totals['views']}
- Total likes: {totals['likes']}
- Total comments: {totals['comments']}
- Total shares: {totals['shares']}
- Total saves: {totals['saves']}
- Total leads: {totals['leads']}

## Best Performing Jobs

| Job ID | Platform | Views | Likes | Leads | URL |
|---|---|---:|---:|---:|---|
{chr(10).join(best_rows)}

## Template Signals

| Template | Jobs | Views | Leads |
|---|---:|---:|---:|
{chr(10).join(template_rows)}

## Notes / Lessons

{notes_block}
"""
