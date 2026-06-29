from __future__ import annotations

from typing import Any

from .autopilot_config import AutopilotConfig


def build_batch_plan(batch_id: str, config: AutopilotConfig, created_at: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "mode": config.mode,
        "status": "planned",
        "trend_count": 0,
        "idea_count": 0,
        "accepted_idea_count": 0,
        "target_platforms": list(config.target_platforms),
        "quality_threshold": config.minimum_quality_score,
        "compliance_required": True,
        "schedule_window": dict(config.schedule_window),
        "created_at": created_at,
        "config": config.to_dict(),
        "completed_stages": [],
        "safety": {
            "live_publishing_enabled": False,
            "scraping_enabled": False,
            "credentials_required": False,
        },
    }
