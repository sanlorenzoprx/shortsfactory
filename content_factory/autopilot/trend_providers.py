from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .autopilot_models import TrendSignal


FIXED_CAPTURED_AT = "2026-06-29T00:00:00+00:00"


class TrendProvider(Protocol):
    key: str

    def collect(self, *, query: str, market: str, locale: str, limit: int) -> list[TrendSignal]: ...


class MockTrendProvider:
    key = "mock"
    _TOPICS = (
        ("contractor proof documentation", 0.88, "rising", "proof gaps delay handoffs and payment"),
        ("appointment no-show recovery", 0.81, "rising", "missed appointments waste local service capacity"),
        ("inspection handoff automation", 0.76, "stable", "small operators need consistent closeout records"),
        ("field service quote follow-up", 0.72, "stable", "slow quote follow-up loses ready buyers"),
        ("specialty clinic intake cleanup", 0.68, "unknown", "manual intake creates avoidable rework"),
    )

    def collect(self, *, query: str, market: str, locale: str, limit: int) -> list[TrendSignal]:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = []
        for index in range(limit):
            topic, strength, velocity, note = self._TOPICS[index % len(self._TOPICS)]
            rows.append(TrendSignal(
                trend_id=f"trend_{index + 1:03d}",
                source=self.key,
                query=query,
                topic=topic,
                market=market,
                locale=locale,
                signal_strength=strength,
                velocity=velocity,
                evidence=({"label": "mock_signal", "value": note, "url": None},),
                captured_at=FIXED_CAPTURED_AT,
            ))
        return rows


class FileTrendProvider:
    key = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def collect(self, *, query: str, market: str, locale: str, limit: int) -> list[TrendSignal]:
        if not self.path.is_file():
            raise ValueError("trend file is missing")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("trend file must contain valid JSON") from exc
        values = payload.get("trends") if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise ValueError("trend file must contain a list")
        rows = []
        for index, value in enumerate(values[:limit]):
            if not isinstance(value, dict):
                raise ValueError("trend entries must be objects")
            candidate = {
                **value,
                "trend_id": str(value.get("trend_id", f"file_trend_{index + 1:03d}")),
                "source": "file",
                "query": str(value.get("query", query)),
                "market": str(value.get("market", market)),
                "locale": str(value.get("locale", locale)),
                "captured_at": str(value.get("captured_at", FIXED_CAPTURED_AT)),
                "evidence": tuple(value.get("evidence", [])),
                "velocity": str(value.get("velocity", "unknown")),
            }
            rows.append(TrendSignal(**candidate))
        if not rows:
            raise ValueError("trend file contains no usable trends")
        return rows
