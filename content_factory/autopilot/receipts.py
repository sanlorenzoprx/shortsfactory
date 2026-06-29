from __future__ import annotations

from typing import Any

from .autopilot_store import ARTIFACTS, AutopilotStore


def build_autopilot_receipt(
    *,
    store: AutopilotStore,
    batch_id: str,
    mode: str,
    created_at: str,
    counts: dict[str, int],
    status: str = "completed",
) -> dict[str, Any]:
    artifacts = {
        key: str(store.path(batch_id, key))
        for key in ARTIFACTS
        if key != "receipt" and store.exists(batch_id, key)
    }
    return {
        "batch_id": batch_id,
        "mode": mode,
        "status": status,
        "created_at": created_at,
        "completed_at": store.now(),
        "counts": counts,
        "artifacts": artifacts,
        "machine_path": [
            "trend_discovery", "idea_generation", "lit_verdict", "verdict_filter",
            "short_generation", "quality_gate", "compliance_gate",
            "simulated_publish", "simulated_analytics", "performance_review",
            "next_batch_plan",
        ],
        "safety": {
            "dry_run": mode == "dry_run",
            "live_publishing_enabled": False,
            "live_publish_attempted": False,
            "platform_api_calls_attempted": False,
            "scraping_attempted": False,
            "browser_posting_attempted": False,
            "credentials_used": False,
            "simulated_publishing_only": True,
            "simulated_analytics_only": True,
        },
        "statement": "No. Phase 5A is dry-run/simulated only.",
    }
