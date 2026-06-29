from __future__ import annotations

from typing import Final


ALLOWED_PLATFORMS: Final[tuple[str, ...]] = (
    "youtube_shorts",
    "tiktok",
    "instagram_reels",
    "other",
)

METRIC_FIELDS: Final[tuple[str, ...]] = (
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "leads",
)

SAFETY_FLAGS: Final[dict[str, object]] = {
    "manual_upload_only": True,
    "api_fetch_attempted": False,
    "api_upload_attempted": False,
    "scraping_attempted": False,
    "live_publishing_enabled": False,
}

LEDGER_FILENAME = "ledger.json"
SUMMARY_FILENAME = "RESULTS_SUMMARY.md"
