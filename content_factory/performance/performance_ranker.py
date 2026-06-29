from __future__ import annotations

from typing import Any


def metric(entry: dict[str, Any], name: str) -> int:
    metrics = entry.get("metrics", {})
    if not isinstance(metrics, dict):
        return 0
    value = metrics.get(name, 0)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def rank_jobs(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank deterministically: leads, views, likes, then oldest first."""
    return sorted(
        entries,
        key=lambda entry: (
            -metric(entry, "leads"),
            -metric(entry, "views"),
            -metric(entry, "likes"),
            str(entry.get("created_at", "")),
            str(entry.get("job_id", "")),
            str(entry.get("platform", "")),
            str(entry.get("entry_id", "")),
        ),
    )
