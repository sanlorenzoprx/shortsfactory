from __future__ import annotations

from content_factory.performance.performance_metrics import build_performance_review
from tests.test_performance_review import manual_entry


def test_zero_views_produces_zero_rates_and_deterministic_experiment():
    review = build_performance_review(
        [manual_entry("zero", views=0, likes=0, comments=0, shares=0, saves=0, leads=0)],
        created_at="2026-06-28T12:00:00+00:00",
    )
    assert set(review["rates"].values()) == {0.0}
    assert review["recommendations"][0]["message"] == (
        "Next experiment: test a different hook/template and record results after manual upload. "
        "This local signal is not statistically proven."
    )


def test_top_jobs_rank_by_leads_views_likes_then_created_at():
    entries = [
        manual_entry("later", job_id="later-job", created_at="2026-06-28T11:00:00+00:00", views=500, likes=50, leads=1),
        manual_entry("older", job_id="older-job", created_at="2026-06-28T09:00:00+00:00", views=500, likes=50, leads=1),
        manual_entry("views", job_id="views-job", views=800, likes=80, leads=0),
        manual_entry("lead", job_id="lead-job", views=10, likes=1, leads=2),
    ]
    review = build_performance_review(entries, created_at="2026-06-28T12:00:00+00:00")
    assert [row["job_id"] for row in review["top_jobs"]] == [
        "lead-job", "older-job", "later-job", "views-job"
    ]


def test_platform_template_quality_and_notes_signals_are_local_and_deterministic():
    entries = [
        manual_entry("one", platform="youtube_shorts", views=100, likes=20, leads=0, quality_score=90),
        manual_entry("two", job_id="job-two", platform="youtube_shorts", views=200, likes=20, leads=0, quality_score=80),
        manual_entry("three", job_id="job-three", platform="tiktok", views=100, likes=5, leads=0, quality_score=100, template_id="script.other"),
    ]
    review = build_performance_review(entries, created_at="2026-06-28T12:00:00+00:00")
    assert review["platform_summary"]["youtube_shorts"]["like_rate"] == 0.13333333
    assert review["template_summary"]["script.default"]["entries"] == 2
    assert review["quality_summary"]["average_quality_score"] == 90
    assert len(review["notes_lessons"]) == 6
    assert "youtube_shorts" in review["recommendations"][0]["message"]
