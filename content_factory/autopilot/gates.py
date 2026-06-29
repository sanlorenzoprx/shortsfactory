from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from content_factory.quality.quality_scorer import PLACEHOLDER_PATTERN, QualityScoringError, evaluate_job

from .autopilot_config import AutopilotConfig
from .autopilot_models import GateResult


CREATED_AT = "2026-06-29T00:05:00+00:00"
FAKE_CERTAINTY = re.compile(r"\b(guaranteed|definitely work|100% chance|risk[- ]free|everyone needs)\b", re.I)
FORBIDDEN_AUTOMATION = re.compile(r"\b(auto[- ]?comment|auto[- ]?dm|fake engagement|scrap(?:e|ing))\b", re.I)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _live_enabled(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key in {"live_publish_enabled", "live_publishing_enabled"} and child is True)
            or _live_enabled(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_live_enabled(child) for child in value)
    return False


class MachineGates:
    def quality(self, jobs: list[dict[str, str]], config: AutopilotConfig) -> list[GateResult]:
        rows = []
        for job in jobs:
            try:
                report = evaluate_job(job["job_id"], config.output_root)
                errors = [issue for issue in report.get("issues", []) if issue.get("severity") == "error"]
                present = set(report.get("present_artifacts", []))
                passed = (
                    int(report.get("overall_score", 0)) >= config.minimum_quality_score
                    and not errors
                    and "short.mp4" in present
                    and "thumbnail.jpg" in present
                    and "receipt.json" in present
                )
                reason = (
                    f"quality score {report.get('overall_score')} meets machine policy"
                    if passed
                    else f"quality score/gates blocked: score={report.get('overall_score')}, errors={len(errors)}"
                )
            except QualityScoringError as exc:
                report = {"error": str(exc), "overall_score": 0, "issues": []}
                passed = False
                reason = str(exc)
            rows.append(GateResult(
                job_id=job["job_id"], gate_name="quality", status="pass" if passed else "fail",
                blocking=not passed, reason=reason,
                source_artifacts=(job["receipt_path"],), created_at=CREATED_AT, details=report,
            ))
        return rows

    def compliance(self, jobs: list[dict[str, str]], config: AutopilotConfig) -> list[GateResult]:
        rows = []
        for job in jobs:
            job_dir = Path(job["job_dir"])
            receipt_path = Path(job["receipt_path"])
            publisher_path = Path(job["publisher_plan"])
            receipt = _read_json(receipt_path)
            publisher = _read_json(publisher_path)
            script = (job_dir / "script.txt").read_text(encoding="utf-8") if (job_dir / "script.txt").is_file() else ""
            combined = f"{script}\n{json.dumps(receipt.get('verdict', {}), ensure_ascii=False)}"
            failures = []
            if config.emergency_stop:
                failures.append("emergency stop is active")
            if not receipt or not isinstance(receipt.get("verdict_provenance"), dict):
                failures.append("LIT verdict provenance is missing")
            if not publisher_path.is_file() or not publisher:
                failures.append("platform metadata is missing")
            if PLACEHOLDER_PATTERN.search(combined):
                failures.append("unresolved placeholder text detected")
            if FAKE_CERTAINTY.search(combined):
                failures.append("fake certainty detected")
            if FORBIDDEN_AUTOMATION.search(combined):
                failures.append("forbidden engagement or scraping language detected")
            if _live_enabled(receipt) or _live_enabled(publisher):
                failures.append("live publishing flag is enabled")
            passed = not failures
            rows.append(GateResult(
                job_id=job["job_id"], gate_name="compliance", status="pass" if passed else "fail",
                blocking=not passed,
                reason="autopilot compliance policy passed" if passed else "; ".join(failures),
                source_artifacts=(str(receipt_path), str(publisher_path)), created_at=CREATED_AT,
                details={"failures": failures, "live_publishing_enabled": False, "scraping_attempted": False},
            ))
        return rows
