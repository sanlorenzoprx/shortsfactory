from __future__ import annotations

from collections import defaultdict
from typing import Any

from .result_models import METRIC_FIELDS


def ledger_totals(entries: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {field: 0 for field in METRIC_FIELDS}
    platforms = sorted(
        {
            str(entry.get("platform"))
            for entry in entries
            if isinstance(entry.get("platform"), str) and entry.get("platform")
        }
    )
    for entry in entries:
        metrics = entry.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        for field in METRIC_FIELDS:
            totals[field] += int(metrics.get(field, 0) or 0)
    return {
        "entries": len(entries),
        "platforms": platforms,
        **totals,
    }


def best_performing_jobs(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(entry: dict[str, Any]) -> tuple[int, int, int, str]:
        metrics = entry.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        return (
            int(metrics.get("views", 0) or 0),
            int(metrics.get("likes", 0) or 0),
            int(metrics.get("leads", 0) or 0),
            str(entry.get("created_at", "")),
        )

    return sorted(entries, key=key, reverse=True)[:10]


def template_signals(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"jobs": set(), "views": 0, "leads": 0}
    )
    for entry in entries:
        context = entry.get("context", {})
        if not isinstance(context, dict):
            continue
        template_ids = context.get("template_ids", {})
        if not isinstance(template_ids, dict):
            continue
        metrics = entry.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        for template_name in template_ids.values():
            if not isinstance(template_name, str) or not template_name:
                continue
            record = aggregates[template_name]
            record["jobs"].add(str(entry.get("job_id", "")))
            record["views"] += int(metrics.get("views", 0) or 0)
            record["leads"] += int(metrics.get("leads", 0) or 0)
    rows = [
        {
            "template": template,
            "jobs": len(values["jobs"]),
            "views": values["views"],
            "leads": values["leads"],
        }
        for template, values in aggregates.items()
    ]
    return sorted(rows, key=lambda row: (row["views"], row["leads"], row["template"]), reverse=True)
