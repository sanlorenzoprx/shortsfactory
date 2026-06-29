from __future__ import annotations

import csv
import io

from content_factory.performance.performance_metrics import build_performance_review
from content_factory.performance.performance_report import (
    render_job_csv,
    render_markdown,
    render_platform_csv,
    render_template_csv,
)
from tests.test_performance_review import manual_entry


def test_markdown_contains_required_sections_notes_and_safety():
    review = build_performance_review([manual_entry("entry")], created_at="2026-06-28T12:00:00+00:00")
    markdown = render_markdown(review)
    for heading in (
        "## Safety Boundary", "## Status", "## Totals", "## Rates",
        "## Best Performing Jobs", "## Platform Summary", "## Template Signals",
        "## Quality Signals", "## Notes and Lessons", "## Recommended Next Manual Experiment",
    ):
        assert heading in markdown
    assert "manual_results_only: true" in markdown
    assert "api_fetch_attempted: false" in markdown
    assert "Keep the direct hook." in markdown


def test_csv_headers_match_phase_4e_contract():
    review = build_performance_review([manual_entry("entry")])
    assert next(csv.reader(io.StringIO(render_platform_csv(review)))) == [
        "platform", "entries", "views", "likes", "comments", "shares", "saves", "leads", "like_rate", "lead_rate"
    ]
    assert next(csv.reader(io.StringIO(render_template_csv(review)))) == [
        "template_id", "entries", "views", "likes", "leads"
    ]
    assert next(csv.reader(io.StringIO(render_job_csv(review)))) == [
        "job_id", "platform", "views", "likes", "comments", "shares", "saves", "leads", "quality_score", "compliance_status"
    ]
