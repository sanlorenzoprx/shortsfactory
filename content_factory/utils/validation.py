from __future__ import annotations

import math
import re
from collections import deque
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List


class LitResponseValidationError(ValueError):
    """Raised when an API response cannot provide a complete verdict."""


_CONTAINER_KEYS = ("deterministicScores", "result", "verdict")
_ALIASES = {
    "verdict_headline": ("verdictHeadline", "verdict_headline", "headline", "verdict"),
    "lit_score": ("litScore", "lit_score", "score", "overallScore"),
    "risk_level": ("riskLevel", "risk_level", "risk"),
    "top_reason": ("topReason", "top_reason", "reason", "primaryReason", "summary"),
    "next_step": ("nextStep", "next_step", "recommendedNextStep", "recommendation"),
    "source": ("source",),
}

_RICH_TEXT_ALIASES = {
    "ghost_town_risk": ("ghost_town_risk", "ghostTownRisk"),
    "buyer_pain_clarity": ("buyer_pain_clarity", "buyerPainClarity"),
    "willingness_to_pay_signal": ("willingness_to_pay_signal", "willingnessToPaySignal"),
    "distribution_difficulty": ("distribution_difficulty", "distributionDifficulty"),
    "unfair_advantage_check": ("unfair_advantage_check", "unfairAdvantageCheck"),
    "business_model_weakness": ("business_model_weakness", "businessModelWeakness"),
    "why_it_might_work": ("why_it_might_work", "whyItMightWork"),
    "why_it_might_fail": ("why_it_might_fail", "whyItMightFail"),
    "killer_question": ("killer_question", "killerQuestion"),
    "mvp_test": ("mvp_test", "mvpTest"),
}
_RICH_RISK_FIELDS = {"ghost_town_risk", "distribution_difficulty"}
_RICH_SIGNAL_FIELDS = {"buyer_pain_clarity", "willingness_to_pay_signal"}


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _candidate_mappings(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    candidates: List[Mapping[str, Any]] = []
    queue = deque([payload])
    seen = set()

    while queue:
        candidate = queue.popleft()
        identity = id(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(candidate)

        normalized = {_normalized_key(key): value for key, value in candidate.items()}
        for container_key in _CONTAINER_KEYS:
            child = normalized.get(_normalized_key(container_key))
            if isinstance(child, Mapping):
                queue.append(child)

    return candidates


def _find_value(candidates: Iterable[Mapping[str, Any]], aliases: Iterable[str]) -> Any:
    normalized_aliases = tuple(_normalized_key(alias) for alias in aliases)
    for candidate in candidates:
        values = {_normalized_key(key): value for key, value in candidate.items()}
        for alias in normalized_aliases:
            value = values.get(alias)
            if value is not None and not isinstance(value, (Mapping, list, tuple)):
                return value
    return None


def _find_complex_value(
    candidates: Iterable[Mapping[str, Any]], aliases: Iterable[str]
) -> Any:
    normalized_aliases = tuple(_normalized_key(alias) for alias in aliases)
    for candidate in candidates:
        values = {_normalized_key(key): value for key, value in candidate.items()}
        for alias in normalized_aliases:
            if alias in values:
                return values[alias]
    return None


def _required_text(candidates: Iterable[Mapping[str, Any]], field: str) -> str:
    value = _find_value(candidates, _ALIASES[field])
    if not isinstance(value, str) or not value.strip():
        raise LitResponseValidationError(f"LIT API response is missing {field}")
    return value.strip()


def _required_score(candidates: Iterable[Mapping[str, Any]]) -> int:
    value = _find_value(candidates, _ALIASES["lit_score"])
    if isinstance(value, bool):
        raise LitResponseValidationError("LIT API response has an invalid lit_score")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise LitResponseValidationError("LIT API response is missing lit_score") from exc
    if not math.isfinite(numeric) or not 0 <= numeric <= 100:
        raise LitResponseValidationError("LIT API response lit_score must be between 0 and 100")
    return round(numeric)


def normalize_lit_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize supported LIT response shapes into complete verdict fields."""

    if not isinstance(payload, Mapping):
        raise LitResponseValidationError("LIT API response must be a JSON object")
    candidates = _candidate_mappings(payload)
    source = _find_value(candidates, _ALIASES["source"])
    normalized = {
        "verdict_headline": _required_text(candidates, "verdict_headline"),
        "lit_score": _required_score(candidates),
        "risk_level": _required_text(candidates, "risk_level"),
        "top_reason": _required_text(candidates, "top_reason"),
        "next_step": _required_text(candidates, "next_step"),
        "source": source.strip() if isinstance(source, str) and source.strip() else "lit_api",
    }
    rich_values = {
        field: _find_value(candidates, aliases)
        for field, aliases in _RICH_TEXT_ALIASES.items()
    }
    missing = sorted(field for field, value in rich_values.items() if value is None)
    api_warnings = _find_complex_value(candidates, ("warnings",))
    warning_values = (
        [item.strip() for item in api_warnings if isinstance(item, str) and item.strip()]
        if isinstance(api_warnings, list)
        else []
    )
    provenance = _find_complex_value(candidates, ("provenance",))

    rich_errors: list[str] = []
    if not missing:
        if normalized["risk_level"] not in {"low", "medium", "high"}:
            rich_errors.append("risk_level has an invalid rich-verdict value")
        for field, value in rich_values.items():
            if not isinstance(value, str) or not value.strip():
                rich_errors.append(f"{field} must be non-empty text")
            elif field in _RICH_RISK_FIELDS and value not in {"low", "medium", "high"}:
                rich_errors.append(f"{field} has an invalid value")
            elif field in _RICH_SIGNAL_FIELDS and value not in {"weak", "medium", "strong"}:
                rich_errors.append(f"{field} has an invalid value")
        if not isinstance(api_warnings, list) or any(
            not isinstance(item, str) for item in api_warnings
        ):
            rich_errors.append("warnings must be an array of strings")
        if not isinstance(provenance, Mapping):
            rich_errors.append("provenance must be an object")
        else:
            if provenance.get("source") != "ai_verdict_engine":
                rich_errors.append("provenance.source must be ai_verdict_engine")
            for field in ("source", "provider", "model"):
                if not isinstance(provenance.get(field), str) or not provenance[field].strip():
                    rich_errors.append(f"provenance.{field} must be non-empty text")
            if provenance.get("validated") is not True:
                rich_errors.append("provenance.validated must be true")
            generated_at = provenance.get("generated_at")
            if not isinstance(generated_at, str) or "T" not in generated_at:
                rich_errors.append("provenance.generated_at must be ISO-8601 text")

    if missing or rich_errors:
        verdict_warning = (
            "rich_verdict_fields_missing"
            if missing
            else "rich_verdict_invalid: " + "; ".join(rich_errors)
        )
        normalized.update({field: "" for field in _RICH_TEXT_ALIASES})
        normalized["verdict_provenance"] = {
            "source": "legacy_lit_api",
            "rich_verdict": False,
        }
        normalized["verdict_warnings"] = [*warning_values, verdict_warning]
        normalized["rich_verdict"] = False
        return normalized

    normalized.update(
        {
            field: str(value).strip()
            for field, value in rich_values.items()
        }
    )
    normalized["verdict_provenance"] = {
        "source": str(provenance["source"]).strip(),
        "provider": str(provenance["provider"]).strip(),
        "model": str(provenance["model"]).strip(),
        "generated_at": str(provenance.get("generated_at", "")).strip(),
        "validated": True,
        "rich_verdict": True,
    }
    normalized["verdict_warnings"] = warning_values
    normalized["rich_verdict"] = True
    return normalized
