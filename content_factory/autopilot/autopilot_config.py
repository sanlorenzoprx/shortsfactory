from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


LIVE_REFUSAL = (
    "Live publishing is not implemented in Phase 5A. Use dry_run or "
    "supervised_autopilot, or implement the approved Phase 5B/5C/5D connector "
    "with official APIs and credentials."
)


class AutopilotRefusal(RuntimeError):
    pass


@dataclass(frozen=True)
class AutopilotConfig:
    mode: str = "dry_run"
    output_root: Path = Path("output")
    trend_query: str = "hottest searched business ideas"
    trend_file: Path | None = None
    trend_provider: str = "mock"
    batch_size: int = 3
    trend_limit: int = 3
    ideas_per_trend: int = 1
    locale: str = "en-US"
    market: str = "US"
    lit_mode: str = "mock"
    minimum_lit_score: int = 55
    strict_rich_verdict: bool = False
    minimum_quality_score: int = 80
    target_platforms: tuple[str, ...] = (
        "youtube_shorts",
        "tiktok",
        "instagram_reels",
    )
    emergency_stop: bool = False
    created_at: str | None = None
    batch_id: str | None = None
    schedule_window: dict[str, str] = field(
        default_factory=lambda: {
            "timezone": "America/Puerto_Rico",
            "not_before": "09:00",
            "not_after": "18:00",
        }
    )

    def __post_init__(self) -> None:
        if self.mode not in {"dry_run", "supervised_autopilot", "full_autopilot"}:
            raise ValueError("invalid autopilot mode")
        if self.batch_size < 1 or self.trend_limit < 1 or self.ideas_per_trend < 1:
            raise ValueError("batch and trend sizes must be positive")
        if not 0 <= self.minimum_lit_score <= 100:
            raise ValueError("minimum_lit_score must be between 0 and 100")
        if not 0 <= self.minimum_quality_score <= 100:
            raise ValueError("minimum_quality_score must be between 0 and 100")
        if self.lit_mode not in {"mock", "api"}:
            raise ValueError("lit_mode must be mock or api")
        if not self.trend_query.strip():
            raise ValueError("trend_query is required")
        if not self.target_platforms:
            raise ValueError("at least one target platform is required")

    def assert_phase_5a_runnable(self) -> None:
        if self.mode == "full_autopilot":
            raise AutopilotRefusal(LIVE_REFUSAL)
        if self.mode == "supervised_autopilot":
            raise AutopilotRefusal(
                "supervised_autopilot is a durable placeholder in Phase 5A; use dry_run until batch approval transitions are enabled."
            )
        if "scrap" in self.trend_provider.casefold():
            raise AutopilotRefusal("Scraping trend providers are forbidden in Phase 5A.")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["output_root"] = str(self.output_root)
        value["trend_file"] = str(self.trend_file) if self.trend_file else None
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AutopilotConfig":
        return cls(
            **{
                **value,
                "output_root": Path(value.get("output_root", "output")),
                "trend_file": Path(value["trend_file"]) if value.get("trend_file") else None,
                "target_platforms": tuple(value.get("target_platforms", ())),
            }
        )
