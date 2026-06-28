from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCORING_VERSION = "phase3d.v1"
STATUS_VALUES = frozenset({"pass", "warn", "fail"})
SEVERITY_VALUES = frozenset({"warning", "error"})
CATEGORY_WEIGHTS = {
    "hook": 15,
    "clarity": 15,
    "cta": 10,
    "captions": 10,
    "media": 15,
    "audio": 10,
    "localization": 10,
    "receipt": 10,
    "publisher_package": 5,
}


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    category: str
    message: str
    suggested_fix: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def issue(
    severity: str,
    category: str,
    message: str,
    suggested_fix: str,
) -> QualityIssue:
    if severity not in SEVERITY_VALUES:
        raise ValueError(f"invalid quality issue severity: {severity}")
    return QualityIssue(severity, category, message, suggested_fix)


def weighted_score(category_scores: dict[str, int]) -> int:
    if set(category_scores) != set(CATEGORY_WEIGHTS):
        raise ValueError("category scores do not match phase3d.v1 categories")
    total = sum(category_scores[name] * weight for name, weight in CATEGORY_WEIGHTS.items())
    return round(total / 100)


def report_is_safe(report: dict[str, Any]) -> bool:
    return (
        report.get("status") in STATUS_VALUES
        and report.get("scoring_version") == SCORING_VERSION
        and report.get("publishing_status") == "not_published"
        and report.get("live_publishing_enabled") is False
    )
