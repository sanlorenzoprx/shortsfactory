from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Protocol

from .autopilot_config import AutopilotConfig, AutopilotRefusal, LIVE_REFUSAL
from .autopilot_models import PublishAttempt


CREATED_AT = "2026-06-29T00:06:00+00:00"


class PublisherAdapter(Protocol):
    platform: str

    def preflight(self, *, config: AutopilotConfig) -> dict[str, object]: ...
    def publish(self, *, attempt: PublishAttempt, package: dict[str, str]) -> PublishAttempt: ...


class SimulatedPublisherAdapter:
    def __init__(self, platform: str):
        self.platform = platform

    def preflight(self, *, config: AutopilotConfig) -> dict[str, object]:
        return {
            "ready": config.mode == "dry_run" and not config.emergency_stop,
            "adapter": "simulated",
            "credentials_required": False,
            "live_publishing_enabled": False,
        }

    def publish(self, *, attempt: PublishAttempt, package: dict[str, str]) -> PublishAttempt:
        if attempt.mode != "dry_run" or attempt.status != "queued":
            raise AutopilotRefusal("simulated publisher accepts queued dry_run attempts only")
        if package.get("metadata_path") != attempt.metadata_path:
            raise AutopilotRefusal("publisher package does not match attempt")
        return replace(attempt, status="simulated_success", finished_at=CREATED_AT)


class RefusingLivePublisherAdapter:
    def __init__(self, platform: str):
        self.platform = platform

    def preflight(self, *, config: AutopilotConfig) -> dict[str, object]:
        return {"ready": False, "reason": LIVE_REFUSAL, "credentials_required": True}

    def publish(self, *, attempt: PublishAttempt, package: dict[str, str]) -> PublishAttempt:
        raise AutopilotRefusal(LIVE_REFUSAL)


def build_publish_queue(
    *, batch_id: str, jobs: list[dict[str, str]], quality: list[dict], compliance: list[dict], config: AutopilotConfig
) -> list[PublishAttempt]:
    quality_map = {row["job_id"]: row for row in quality}
    compliance_map = {row["job_id"]: row for row in compliance}
    attempts = []
    for job in jobs:
        ready = not quality_map[job["job_id"]]["blocking"] and not compliance_map[job["job_id"]]["blocking"]
        for platform in config.target_platforms:
            digest = hashlib.sha256(f"{batch_id}:{job['job_id']}:{platform}".encode("utf-8")).hexdigest()[:12]
            attempts.append(PublishAttempt(
                publish_attempt_id=f"pub_{digest}", batch_id=batch_id, job_id=job["job_id"],
                platform=platform, mode=config.mode, adapter="simulated",
                status="queued" if ready else "blocked", external_post_id=None, external_url=None,
                blocked_reason=None if ready else "machine quality or compliance gate failed",
                metadata_path=job["publisher_plan"], created_at=CREATED_AT, finished_at=None,
            ))
    return attempts
