from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from .autopilot_models import AnalyticsSnapshot, PublishAttempt


CAPTURED_AT = "2026-06-29T00:07:00+00:00"


class AnalyticsAdapter(Protocol):
    platform: str

    def collect(self, *, published_item: PublishAttempt) -> AnalyticsSnapshot: ...


class SimulatedAnalyticsAdapter:
    def __init__(self, platform: str):
        self.platform = platform

    def collect(self, *, published_item: PublishAttempt) -> AnalyticsSnapshot:
        if published_item.status != "simulated_success" or published_item.platform != self.platform:
            raise ValueError("simulated analytics requires a matching simulated publish")
        digest = hashlib.sha256(published_item.publish_attempt_id.encode("utf-8")).hexdigest()
        views = 100 + int(digest[:4], 16) % 901
        likes = views * (3 + int(digest[4:6], 16) % 8) // 100
        comments = int(digest[6:8], 16) % 8
        shares = int(digest[8:10], 16) % 10
        saves = int(digest[10:12], 16) % 7
        leads = int(digest[12:14], 16) % 3
        return AnalyticsSnapshot(
            snapshot_id=f"ana_{digest[:12]}", batch_id=published_item.batch_id,
            job_id=published_item.job_id, platform=self.platform, source="simulated",
            metrics={"views": views, "likes": likes, "comments": comments, "shares": shares, "saves": saves, "leads": leads},
            captured_at=CAPTURED_AT,
        )


class FileAnalyticsAdapter:
    def __init__(self, platform: str, path: str | Path):
        self.platform = platform
        self.path = Path(path).expanduser().resolve()

    def collect(self, *, published_item: PublishAttempt) -> AnalyticsSnapshot:
        values = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError("analytics file must contain a list")
        for value in values:
            if isinstance(value, dict) and value.get("job_id") == published_item.job_id and value.get("platform") == self.platform:
                return AnalyticsSnapshot.from_dict(value)
        raise ValueError("analytics snapshot is missing for publish attempt")
