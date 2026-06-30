from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .creative_angle_models import AngleShortJob, CreativeAnglePack, LongFormAssemblyPlan


RECEIPT_VERSION = "phase5b.5b.creative-pack-comparison.v1"
WORD = re.compile(r"[a-z0-9]{4,}", re.I)
STOP = {"this", "that", "with", "from", "your", "before", "after", "ghosttowntest"}


class CreativePackComparisonError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CreativePackComparisonError(f"{label} is missing or invalid") from exc
    if not isinstance(value, dict):
        raise CreativePackComparisonError(f"{label} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=".creative-comparison.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _specificity(script: str) -> dict[str, int]:
    words = [word.casefold() for word in WORD.findall(script) if word.casefold() not in STOP]
    return {
        "word_count": len(words),
        "unique_specific_words": len(set(words)),
        "action_terms": sum(word in {"ask", "test", "build", "sell", "prove", "identify", "run"} for word in words),
    }


class CreativePackComparator:
    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.output_root = Path(output_root).expanduser().resolve()
        self.now = now

    def compare(self, *, left: str | Path, right: str | Path) -> tuple[dict[str, Any], Path]:
        left_value = self._load(Path(left).expanduser().resolve())
        right_value = self._load(Path(right).expanduser().resolve())
        left_pack, left_jobs, left_longform, left_quality = left_value
        right_pack, right_jobs, right_longform, right_quality = right_value
        left_map = {job.angle_id: job for job in left_jobs}
        right_map = {job.angle_id: job for job in right_jobs}
        angle_ids = [angle.angle_id for angle in left_pack.angles]
        if set(angle_ids) != set(right_map):
            raise CreativePackComparisonError("creative packs do not cover the same angle IDs")
        angle_comparisons = []
        for angle_id in angle_ids:
            left_job = left_map[angle_id]
            right_job = right_map[angle_id]
            left_specificity = _specificity(left_job.script)
            right_specificity = _specificity(right_job.script)
            angle_comparisons.append({
                "angle_id": angle_id,
                "hook": {"left": left_job.hook, "right": right_job.hook, "same": left_job.hook == right_job.hook},
                "title": {"left": left_job.title, "right": right_job.title, "same": left_job.title == right_job.title},
                "thumbnail_text": {
                    "left": left_job.thumbnail_text,
                    "right": right_job.thumbnail_text,
                    "same": left_job.thumbnail_text == right_job.thumbnail_text,
                },
                "cta": {"left": left_job.cta, "right": right_job.cta, "same": left_job.cta == right_job.cta},
                "script_specificity": {
                    "left": left_specificity,
                    "right": right_specificity,
                    "unique_word_delta": right_specificity["unique_specific_words"] - left_specificity["unique_specific_words"],
                },
            })
        timestamp = self.now().astimezone(timezone.utc)
        identity = {
            "left": left_pack.angle_pack_id,
            "right": right_pack.angle_pack_id,
            "timestamp": timestamp.isoformat(),
        }
        comparison_id = "cpc_" + hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        receipt = {
            "receipt_version": RECEIPT_VERSION,
            "comparison_id": comparison_id,
            "timestamp": timestamp.isoformat(),
            "left": self._source_summary(left_pack, Path(left), left_quality),
            "right": self._source_summary(right_pack, Path(right), right_quality),
            "angle_comparisons": angle_comparisons,
            "angle_uniqueness": {
                "left": len(set(left_map)) == len(left_map) == 5,
                "right": len(set(right_map)) == len(right_map) == 5,
            },
            "longform_completeness": {
                "left": len(left_longform.source_short_job_ids) == len(left_longform.ordered_chapters) == 5,
                "right": len(right_longform.source_short_job_ids) == len(right_longform.ordered_chapters) == 5,
            },
            "quality_gate_result": {"left": left_quality, "right": right_quality},
            "summary": {
                "same_hooks": sum(row["hook"]["same"] for row in angle_comparisons),
                "same_titles": sum(row["title"]["same"] for row in angle_comparisons),
                "same_thumbnails": sum(row["thumbnail_text"]["same"] for row in angle_comparisons),
                "same_ctas": sum(row["cta"]["same"] for row in angle_comparisons),
            },
            "safety": {
                "network_called": False,
                "publish_attempted": False,
                "youtube_api_called": False,
                "videos_insert_called": False,
                "secrets_recorded": False,
                "full_autopilot_enabled": False,
            },
            "status": "completed",
        }
        path = (
            self.output_root / "creative_angle_packs" / "comparisons"
            / f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_CREATIVE_PACK_COMPARISON.json"
        )
        _atomic_json(path, receipt)
        _read_object(path, "comparison receipt")
        return receipt, path

    @staticmethod
    def _load(
        path: Path,
    ) -> tuple[CreativeAnglePack, tuple[AngleShortJob, ...], LongFormAssemblyPlan, bool]:
        pack = CreativeAnglePack.from_dict(_read_object(path, "creative angle pack"))
        directory = path.parent
        jobs = tuple(
            AngleShortJob.from_dict(_read_object(
                directory / "shorts" / angle.angle_id / "angle_short_job.json",
                f"short job {angle.angle_id}",
            ))
            for angle in pack.angles
        )
        longform = LongFormAssemblyPlan.from_dict(_read_object(
            directory / "longform" / "LONGFORM_ASSEMBLY_PLAN.json",
            "long-form assembly plan",
        ))
        source_receipt = _read_object(directory / "ANGLE_PACK_RECEIPT.json", "angle pack receipt")
        gates = source_receipt.get("gates", [])
        quality_passed = (
            source_receipt.get("status") in {"completed", "passed"}
            and isinstance(gates, list)
            and not any(isinstance(gate, dict) and gate.get("blocking") for gate in gates)
        )
        return pack, jobs, longform, quality_passed

    @staticmethod
    def _source_summary(pack: CreativeAnglePack, path: Path, quality_passed: bool) -> dict[str, Any]:
        return {
            "angle_pack_id": pack.angle_pack_id,
            "provider_type": pack.provider_type,
            "model_id": pack.model_id,
            "creative_angle_pack": str(path.resolve()),
            "quality_gates_passed": quality_passed,
        }
