from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .performance_models import METRIC_FIELDS, SAFETY_FLAGS
from .performance_ranker import metric, rank_jobs


def _rate(numerator: int, views: int) -> float:
    return round(numerator / views, 8) if views else 0.0


def _metrics(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {field: sum(metric(entry, field) for entry in entries) for field in METRIC_FIELDS}


def _platform_summary(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry.get("platform", "other"))].append(entry)
    summary: dict[str, dict[str, Any]] = {}
    for platform in sorted(grouped):
        values = _metrics(grouped[platform])
        summary[platform] = {
            "entries": len(grouped[platform]),
            **values,
            "like_rate": _rate(values["likes"], values["views"]),
            "lead_rate": _rate(values["leads"], values["views"]),
        }
    return summary


def _template_summary(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        context = entry.get("context", {})
        template_ids = context.get("template_ids", {}) if isinstance(context, dict) else {}
        if not isinstance(template_ids, dict):
            continue
        for template_id in sorted({str(value) for value in template_ids.values() if value}):
            grouped[template_id].append(entry)
    summary: dict[str, dict[str, int]] = {}
    for template_id in sorted(grouped):
        values = _metrics(grouped[template_id])
        summary[template_id] = {
            "entries": len(grouped[template_id]),
            "views": values["views"],
            "likes": values["likes"],
            "leads": values["leads"],
        }
    return summary


def _quality_summary(entries: list[dict[str, Any]]) -> dict[str, float | int | None]:
    scores: list[float] = []
    for entry in entries:
        context = entry.get("context", {})
        score = context.get("quality_score") if isinstance(context, dict) else None
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(float(score))
    if not scores:
        return {
            "average_quality_score": None,
            "best_quality_score": None,
            "worst_quality_score": None,
        }
    average = round(sum(scores) / len(scores), 4)
    return {
        "average_quality_score": int(average) if average.is_integer() else average,
        "best_quality_score": int(max(scores)) if max(scores).is_integer() else max(scores),
        "worst_quality_score": int(min(scores)) if min(scores).is_integer() else min(scores),
    }


def _job_summary(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in rank_jobs(entries):
        context = entry.get("context", {})
        if not isinstance(context, dict):
            context = {}
        rows.append(
            {
                "entry_id": str(entry.get("entry_id", "")),
                "job_id": str(entry.get("job_id", "")),
                "platform": str(entry.get("platform", "")),
                **{field: metric(entry, field) for field in METRIC_FIELDS},
                "score": context.get("quality_score"),
                "quality_score": context.get("quality_score"),
                "compliance_status": context.get("compliance_status"),
                "created_at": str(entry.get("created_at", "")),
            }
        )
    return rows


def _notes_lessons(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in sorted(entries, key=lambda item: (str(item.get("created_at", "")), str(item.get("entry_id", "")))):
        note = str(entry.get("notes", "")).strip()
        if note:
            rows.append({"job_id": str(entry.get("job_id", "")), "type": "note", "message": note})
        lessons = entry.get("lessons", [])
        if isinstance(lessons, list):
            for lesson in lessons:
                message = str(lesson).strip()
                if message:
                    rows.append({"job_id": str(entry.get("job_id", "")), "type": "lesson", "message": message})
    return rows


def _recommendation(
    entries: list[dict[str, Any]],
    platforms: dict[str, dict[str, Any]],
    templates: dict[str, dict[str, int]],
) -> str:
    if not entries:
        return "Record at least one manual result before choosing the next experiment."
    totals = _metrics(entries)
    if all(totals[field] == 0 for field in METRIC_FIELDS):
        return "Next experiment: test a different hook/template and record results after manual upload. This local signal is not statistically proven."
    if totals["leads"] > 0:
        platform = sorted(
            platforms,
            key=lambda name: (-int(platforms[name]["leads"]), -int(platforms[name]["views"]), -int(platforms[name]["likes"]), name),
        )[0]
        template = sorted(
            templates,
            key=lambda name: (-int(templates[name]["leads"]), -int(templates[name]["views"]), -int(templates[name]["likes"]), name),
        )[0] if templates else "the strongest recorded template"
        return f"Next experiment: create another short for {platform} using {template}, based on the strongest local lead signal. This manual result is not statistically proven."
    platform = sorted(
        platforms,
        key=lambda name: (-float(platforms[name]["like_rate"]), -int(platforms[name]["views"]), -int(platforms[name]["likes"]), name),
    )[0]
    return f"Next experiment: test {platform}, the strongest local engagement signal, again with a clearer CTA. This manual result is not statistically proven."


def build_performance_review(
    entries: list[dict[str, Any]],
    *,
    results_root: str | Path = "results_ledger",
    created_at: str | None = None,
) -> dict[str, Any]:
    totals_values = _metrics(entries)
    platforms = _platform_summary(entries)
    templates = _template_summary(entries)
    quality = _quality_summary(entries)
    warnings: list[str] = []
    if entries and quality["average_quality_score"] is None:
        warnings.append("No captured quality scores are available in the manual entries.")
    if entries and not templates:
        warnings.append("No template provenance is available in the manual entries.")
    status = "empty" if not entries else ("partial" if warnings else "ready")
    recommendation = _recommendation(entries, platforms, templates)
    jobs = _job_summary(entries)
    return {
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source": {"results_root": str(Path(results_root)), "entry_count": len(entries)},
        "totals": {
            "entries": len(entries),
            "platforms": len(platforms),
            **totals_values,
        },
        "rates": {
            "like_rate": _rate(totals_values["likes"], totals_values["views"]),
            "comment_rate": _rate(totals_values["comments"], totals_values["views"]),
            "share_rate": _rate(totals_values["shares"], totals_values["views"]),
            "save_rate": _rate(totals_values["saves"], totals_values["views"]),
            "lead_rate": _rate(totals_values["leads"], totals_values["views"]),
        },
        "top_jobs": jobs[:10],
        "job_summary": jobs,
        "platform_summary": platforms,
        "template_summary": templates,
        "quality_summary": quality,
        "notes_lessons": _notes_lessons(entries),
        "recommendations": [{"type": "manual_experiment", "message": recommendation}],
        "safety": dict(SAFETY_FLAGS),
        "warnings": warnings,
    }
