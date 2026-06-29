from __future__ import annotations

import csv
import io
from typing import Any

from .performance_models import SAFETY_FLAGS


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _score(value: object) -> str:
    return "Not available" if value is None else str(value)


def render_markdown(review: dict[str, Any]) -> str:
    totals = review["totals"]
    rates = review["rates"]
    job_rows = [
        f"| {index} | {_cell(row['job_id'])} | {_cell(row['platform'])} | {row['views']} | {row['likes']} | {row['leads']} | {_score(row['quality_score'])} |"
        for index, row in enumerate(review["top_jobs"], 1)
    ] or ["| - | None | None | 0 | 0 | 0 | Not available |"]
    platform_rows = [
        f"| {_cell(platform)} | {row['entries']} | {row['views']} | {row['likes']} | {row['leads']} | {row['like_rate']:.4%} | {row['lead_rate']:.4%} |"
        for platform, row in review["platform_summary"].items()
    ] or ["| None | 0 | 0 | 0 | 0 | 0.0000% | 0.0000% |"]
    template_rows = [
        f"| {_cell(template)} | {row['entries']} | {row['views']} | {row['likes']} | {row['leads']} |"
        for template, row in review["template_summary"].items()
    ] or ["| None | 0 | 0 | 0 | 0 |"]
    notes = [
        f"- {_cell(row['job_id'])} ({_cell(row['type'])}): {_cell(row['message'])}"
        for row in review["notes_lessons"]
    ] or ["- None recorded."]
    warning_lines = [f"- {_cell(value)}" for value in review["warnings"]] or ["- None."]
    empty_message = ""
    if review["status"] == "empty":
        empty_message = "\nNo manual results recorded yet.\nRecord a result with results_ledger.py before reviewing performance.\n"
    quality = review["quality_summary"]
    recommendation = review["recommendations"][0]["message"]
    return f"""# Local Performance Review

## Safety Boundary

All performance data is manually entered.
No platform APIs were called.
No scraping was attempted.
Shorts Factory did not publish or fetch these results.

- manual_results_only: {str(SAFETY_FLAGS['manual_results_only']).lower()}
- api_fetch_attempted: {str(SAFETY_FLAGS['api_fetch_attempted']).lower()}
- api_upload_attempted: {str(SAFETY_FLAGS['api_upload_attempted']).lower()}
- scraping_attempted: {str(SAFETY_FLAGS['scraping_attempted']).lower()}
- live_publishing_enabled: {str(SAFETY_FLAGS['live_publishing_enabled']).lower()}

## Status

{str(review['status']).title()}
{empty_message}
## Totals

- Entries: {totals['entries']}
- Platforms: {totals['platforms']}
- Views: {totals['views']}
- Likes: {totals['likes']}
- Comments: {totals['comments']}
- Shares: {totals['shares']}
- Saves: {totals['saves']}
- Leads: {totals['leads']}

## Rates

- Like rate: {rates['like_rate']:.4%}
- Comment rate: {rates['comment_rate']:.4%}
- Share rate: {rates['share_rate']:.4%}
- Save rate: {rates['save_rate']:.4%}
- Lead rate: {rates['lead_rate']:.4%}

## Best Performing Jobs

| Rank | Job ID | Platform | Views | Likes | Leads | Quality Score |
|---:|---|---|---:|---:|---:|---:|
{chr(10).join(job_rows)}

## Platform Summary

| Platform | Entries | Views | Likes | Leads | Like Rate | Lead Rate |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(platform_rows)}

## Template Signals

| Template | Entries | Views | Likes | Leads |
|---|---:|---:|---:|---:|
{chr(10).join(template_rows)}

## Quality Signals

- Average quality score: {_score(quality['average_quality_score'])}
- Best quality score: {_score(quality['best_quality_score'])}
- Worst quality score: {_score(quality['worst_quality_score'])}

## Notes and Lessons

{chr(10).join(notes)}

## Recommended Next Manual Experiment

{recommendation}

## Warnings

{chr(10).join(warning_lines)}
"""


def _csv(rows: list[dict[str, Any]], headers: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_platform_csv(review: dict[str, Any]) -> str:
    headers = ["platform", "entries", "views", "likes", "comments", "shares", "saves", "leads", "like_rate", "lead_rate"]
    rows = [{"platform": platform, **values} for platform, values in review["platform_summary"].items()]
    return _csv(rows, headers)


def render_template_csv(review: dict[str, Any]) -> str:
    headers = ["template_id", "entries", "views", "likes", "leads"]
    rows = [{"template_id": template, **values} for template, values in review["template_summary"].items()]
    return _csv(rows, headers)


def render_job_csv(review: dict[str, Any]) -> str:
    headers = ["job_id", "platform", "views", "likes", "comments", "shares", "saves", "leads", "quality_score", "compliance_status"]
    rows = [{header: row.get(header, "") for header in headers} for row in review["job_summary"]]
    return _csv(rows, headers)
