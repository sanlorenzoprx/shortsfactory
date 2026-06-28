from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


FLOW_STEPS = (
    "generate",
    "score",
    "mission_control_review",
    "revision",
    "rescore",
    "approval",
    "export",
    "upload_kit",
    "template_control",
)

SAFETY_STATUS = {
    "live_publishing_enabled": False,
    "api_upload_attempted": False,
    "manual_upload_only": True,
    "real_user_recording": False,
    "scraping": False,
    "external_database": False,
}


@dataclass(frozen=True)
class AuditResult:
    audit_receipt: dict[str, Any]
    report_path: Path
    demo_root: Path
    original_job_id: str
    revised_job_id: str
