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
    return {
        "verdict_headline": _required_text(candidates, "verdict_headline"),
        "lit_score": _required_score(candidates),
        "risk_level": _required_text(candidates, "risk_level"),
        "top_reason": _required_text(candidates, "top_reason"),
        "next_step": _required_text(candidates, "next_step"),
        "source": source.strip() if isinstance(source, str) and source.strip() else "lit_api",
    }
