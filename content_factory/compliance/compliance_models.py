from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


JSON_NAME = "COMPLIANCE_CHECKLIST.json"
MARKDOWN_NAME = "COMPLIANCE_CHECKLIST.md"

SAFETY_FLAGS = {
    "manual_upload_only": True,
    "publishing_status": "not_published",
    "live_publishing_enabled": False,
    "api_upload_attempted": False,
    "requires_human_upload": True,
}

STATUS_NEEDS_REVIEW = "needs_human_review"
STATUS_READY = "ready_for_manual_upload"

HUMAN_REVIEW_ITEMS = (
    ("title_is_accurate", "Title/caption accurately represents the video"),
    ("no_unsupported_claims", "No unsupported claims"),
    ("no_false_urgency", "No false urgency or misleading promise"),
    ("cta_is_appropriate", "CTA is appropriate"),
    ("captions_are_readable", "Captions are readable"),
    ("hashtags_are_appropriate", "Hashtags are appropriate"),
    ("preview_looks_correct", "Platform preview looks correct"),
    ("final_video_watched", "Final video was watched before upload"),
    ("manual_upload_confirmed", "This will be uploaded manually by a human"),
)


@dataclass(frozen=True)
class ComplianceResult:
    job_id: str
    compliance_dir: Path
    checklist: dict[str, Any]
