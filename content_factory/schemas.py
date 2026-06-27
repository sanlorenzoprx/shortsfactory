from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Idea:
    name: str
    description: str
    target_user: str = "early-stage builders"
    market: str = "US"


@dataclass(frozen=True)
class LitVerdict:
    idea: Idea
    verdict_headline: str
    lit_score: int
    risk_level: str
    top_reason: str
    next_step: str
    source: str = "mock"


@dataclass(frozen=True)
class AppTestOutcome:
    verdict: LitVerdict
    raw_response: Optional[Dict[str, Any]] = None
    warning: Optional[str] = None


@dataclass(frozen=True)
class ShortScript:
    hook: str
    body_lines: List[str]
    verdict_reveal: str
    cta: str

    def as_text(self) -> str:
        return "\n".join([self.hook, *self.body_lines, self.verdict_reveal, self.cta])


@dataclass
class ShortJobReceipt:
    job_id: str = field(default_factory=lambda: uuid4().hex[:12])
    created_at: str = field(default_factory=utc_now_iso)
    locale: str = "en-US"
    mode: str = "mock"
    idea: Dict[str, Any] = field(default_factory=dict)
    verdict: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    recording: Dict[str, Any] = field(default_factory=lambda: {"enabled": False})
    voiceover: Dict[str, Any] = field(default_factory=lambda: {"status": "disabled"})
    music: Dict[str, Any] = field(default_factory=lambda: {"status": "disabled"})
    localization: Dict[str, Any] = field(default_factory=dict)
    queue: Dict[str, Any] = field(default_factory=lambda: {"status": "disabled"})
    scheduler: Dict[str, Any] = field(default_factory=lambda: {"status": "disabled"})

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)
