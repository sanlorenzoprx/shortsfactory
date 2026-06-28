from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEARCH_ROOTS = (Path("jobs"), Path("phase2g-acceptance") / "jobs")

ARTIFACT_CANDIDATES: dict[str, tuple[Path, ...]] = {
    "short.mp4": (Path("short.mp4"),),
    "short_with_voice.mp4": (Path("short_with_voice.mp4"),),
    "short_with_music.mp4": (
        Path("short_with_music.mp4"),
        Path("short_with_voice_and_music.mp4"),
    ),
    "final.mp4": (Path("final.mp4"),),
    "thumbnail.jpg": (Path("thumbnail.jpg"),),
    "captions.srt": (Path("captions.srt"),),
    "script.txt": (Path("script.txt"),),
    "receipt.json": (Path("receipt.json"),),
    "lit_api_response.json": (Path("lit_api_response.json"),),
    "app_recording.mp4": (Path("app_recording.mp4"),),
    "app_recording_final.png": (Path("app_recording_final.png"),),
    "publisher_package.json": (
        Path("publisher_package.json"),
        Path("publish") / "publisher_package.json",
        Path("publish") / "publisher_plan.json",
    ),
}


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_dir: Path
    created_at: str
    locale: str
    mode: str
    source: str
    status: str
    warnings: tuple[str, ...]
    artifacts: dict[str, Path]
    receipt: dict[str, Any]

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


def _text(value: Any, default: str = "unknown") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _warnings(receipt: dict[str, Any], load_warning: str | None) -> tuple[str, ...]:
    values = receipt.get("warnings", [])
    if not isinstance(values, list):
        values = [values]
    warnings = [str(value) for value in values if value not in (None, "")]
    if load_warning:
        warnings.append(load_warning)
    return tuple(warnings)


def _load_receipt(receipt_path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("receipt root must be a JSON object")
        return value, None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {}, f"Could not read receipt.json: {exc}"


def _detect_artifacts(job_dir: Path, output_root: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {}
    for name, candidates in ARTIFACT_CANDIDATES.items():
        for relative_path in candidates:
            candidate = job_dir / relative_path
            if candidate.is_file() and is_within(candidate, output_root):
                artifacts[name] = candidate.resolve()
                break
    return artifacts


def _build_job(job_dir: Path, output_root: Path) -> JobRecord:
    receipt, load_warning = _load_receipt(job_dir / "receipt.json")
    verdict = receipt.get("verdict", {})
    if not isinstance(verdict, dict):
        verdict = {}
    publisher = receipt.get("publisher", {})
    if not isinstance(publisher, dict):
        publisher = {}
    job_id = _text(receipt.get("job_id"), job_dir.name)
    return JobRecord(
        job_id=job_id,
        job_dir=job_dir.resolve(),
        created_at=_text(receipt.get("created_at"), "not recorded"),
        locale=_text(receipt.get("locale")),
        mode=_text(receipt.get("mode")),
        source=_text(receipt.get("source") or verdict.get("source")),
        status=_text(receipt.get("status") or publisher.get("status"), "complete"),
        warnings=_warnings(receipt, load_warning),
        artifacts=_detect_artifacts(job_dir, output_root),
        receipt=receipt,
    )


def scan_jobs(output_root: str | Path) -> list[JobRecord]:
    """Return receipt-backed jobs from the two Phase 3A job roots."""
    root = Path(output_root).expanduser().resolve()
    jobs: list[JobRecord] = []
    for relative_root in SEARCH_ROOTS:
        jobs_root = root / relative_root
        if not jobs_root.is_dir() or not is_within(jobs_root, root):
            continue
        try:
            candidates = list(jobs_root.iterdir())
        except OSError:
            continue
        for job_dir in candidates:
            receipt_path = job_dir / "receipt.json"
            if (
                job_dir.is_dir()
                and is_within(job_dir, root)
                and receipt_path.is_file()
                and is_within(receipt_path, root)
            ):
                jobs.append(_build_job(job_dir, root))
    return sorted(jobs, key=lambda job: (job.created_at, job.job_id), reverse=True)


def find_job(output_root: str | Path, job_id: str) -> JobRecord | None:
    """Find an indexed job by its receipt job ID without accepting a path."""
    return next((job for job in scan_jobs(output_root) if job.job_id == job_id), None)
