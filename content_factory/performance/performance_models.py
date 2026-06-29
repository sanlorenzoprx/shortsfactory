from __future__ import annotations

from typing import Final


REPORT_JSON: Final[str] = "PERFORMANCE_REVIEW.json"
REPORT_MARKDOWN: Final[str] = "PERFORMANCE_REVIEW.md"
PLATFORM_CSV: Final[str] = "platform_summary.csv"
TEMPLATE_CSV: Final[str] = "template_summary.csv"
JOB_CSV: Final[str] = "job_summary.csv"

SAFETY_FLAGS: Final[dict[str, object]] = {
    "manual_results_only": True,
    "api_fetch_attempted": False,
    "api_upload_attempted": False,
    "scraping_attempted": False,
    "live_publishing_enabled": False,
}

METRIC_FIELDS: Final[tuple[str, ...]] = (
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "leads",
)
