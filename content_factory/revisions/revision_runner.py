from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from content_factory.agents.caption_agent import CaptionAgent
from content_factory.agents.script_writer import ScriptWriter
from content_factory.agents.thumbnail_agent import ThumbnailAgent
from content_factory.agents.video_builder import VideoBuilder
from content_factory.config import Config
from content_factory.mission_control.approvals import ApprovalStore, validate_job_id
from content_factory.mission_control.job_index import JobRecord, find_job, is_within
from content_factory.schemas import Idea, LitVerdict, ShortScript

from .revision_manifest import (
    MANIFEST_NAME,
    build_revision_manifest,
    read_revision_manifest,
    write_revision_manifest,
)
from .revision_queue import RevisionQueue, RevisionTaskError, utc_now_iso


class RevisionRunError(RuntimeError):
    """A safe, user-facing refusal or failure to revise a job."""


@dataclass(frozen=True)
class RevisionResult:
    original_job_id: str
    revised_job_id: str
    revised_job_dir: Path
    revision_note: str
    manifest: dict[str, Any]


def _revised_job_id(original_job_id: str, note: str) -> str:
    digest = hashlib.sha256(f"{original_job_id}\0{note}".encode("utf-8")).hexdigest()[:10]
    return validate_job_id(f"{original_job_id[:40]}-r{digest}")


def _verdict_from_job(job: JobRecord) -> LitVerdict:
    value = job.receipt.get("verdict", {})
    if not isinstance(value, dict) or not value:
        verdict_path = job.job_dir / "verdict.json"
        try:
            value = json.loads(verdict_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RevisionRunError(f"job {job.job_id} has no usable verdict") from exc
    idea_value = value.get("idea") or job.receipt.get("idea")
    if not isinstance(idea_value, dict) or not idea_value.get("name"):
        raise RevisionRunError(f"job {job.job_id} has no usable idea")
    try:
        idea = Idea(
            name=str(idea_value["name"]),
            description=str(idea_value.get("description", "")),
            target_user=str(idea_value.get("target_user", "early-stage builders")),
            market=str(idea_value.get("market", "US")),
        )
        return LitVerdict(
            idea=idea,
            verdict_headline=str(value.get("verdict_headline", "Review this idea")),
            lit_score=int(value.get("lit_score", 0)),
            risk_level=str(value.get("risk_level", "unknown")),
            top_reason=str(value.get("top_reason", "Human review requested a revision.")),
            next_step=str(value.get("next_step", "Review the revised short.")),
            source=str(value.get("source", "revision_source")),
        )
    except (TypeError, ValueError) as exc:
        raise RevisionRunError(f"job {job.job_id} has an invalid verdict") from exc


def _script_from_job(job: JobRecord, verdict: LitVerdict, locale: str) -> ShortScript:
    path = job.artifacts.get("script.txt")
    if path is None:
        return ScriptWriter().generate_script(verdict, locale=locale)
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError) as exc:
        raise RevisionRunError(f"could not read script for job {job.job_id}") from exc
    if len(lines) < 2:
        return ScriptWriter().generate_script(verdict, locale=locale)
    if len(lines) == 2:
        return ShortScript(hook=lines[0], body_lines=[], verdict_reveal="", cta=lines[1])
    return ShortScript(
        hook=lines[0],
        body_lines=lines[1:-2],
        verdict_reveal=lines[-2],
        cta=lines[-1],
    )


def _trim_line(value: str, limit: int = 78) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip(" ,.;:-") + "…"


def revise_script(
    script: ShortScript,
    note: str,
    idea_name: str,
    locale: str,
) -> ShortScript:
    """Apply deliberately small, deterministic human-note rules."""
    lowered = note.casefold()
    hook_requested = "hook" in lowered
    cta_requested = "cta" in lowered or "call to action" in lowered
    shorter_requested = any(token in lowered for token in ("shorter", "trim", "too long"))
    locale_requested = "spanish" in lowered or "es-pr" in lowered
    hook = script.hook
    body = list(script.body_lines)
    reveal = script.verdict_reveal
    cta = script.cta

    if hook_requested:
        hook = (
            f"Detente y prueba esta idea: {idea_name}."
            if locale == "es-PR"
            else f"Test this before you build: {idea_name}."
        )
    if cta_requested:
        cta = (
            "Prueba esta idea ahora antes de construir."
            if locale == "es-PR"
            else "Test this idea now, then decide what to build."
        )
    if shorter_requested:
        hook = _trim_line(hook)
        body = [_trim_line(line) for line in body[:2]]
        reveal = _trim_line(reveal)
        cta = _trim_line(cta)
    if not (hook_requested or cta_requested or shorter_requested):
        prefix = "Enfoque de revisión" if locale == "es-PR" and locale_requested else "Revision focus"
        body.append(f"{prefix}: {_trim_line(note, 120)}")
    return ShortScript(hook=hook, body_lines=body, verdict_reveal=reveal, cta=cta)


def _completed_result(
    output_root: Path, task: dict[str, Any]
) -> RevisionResult | None:
    revised_job_id = task.get("revised_job_id")
    if task.get("state") != "revision_complete" or not isinstance(revised_job_id, str):
        return None
    job = find_job(output_root, revised_job_id)
    if job is None:
        return None
    manifest = read_revision_manifest(job.artifacts.get(MANIFEST_NAME))
    if manifest is None:
        return None
    return RevisionResult(
        original_job_id=str(task["job_id"]),
        revised_job_id=revised_job_id,
        revised_job_dir=job.job_dir,
        revision_note=str(task["revision_note"]),
        manifest=manifest,
    )


def _safe_replace_job(temporary_dir: Path, destination: Path, output_root: Path, original_id: str) -> None:
    if destination.exists() or destination.is_symlink():
        if not is_within(destination, output_root) or destination.is_symlink() or not destination.is_dir():
            raise RevisionRunError("existing revised job path is not a safe directory")
        receipt_path = destination / "receipt.json"
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RevisionRunError("existing revised job does not have valid lineage") from exc
        revision = existing.get("revision", {}) if isinstance(existing, dict) else {}
        if revision.get("original_job_id") != original_id:
            raise RevisionRunError("existing revised job belongs to another source job")
        shutil.rmtree(destination)
    temporary_dir.replace(destination)


def run_revision(
    job_id: str,
    output_root: str | Path = "output",
    note: str | None = None,
) -> RevisionResult:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise RevisionRunError("invalid job_id") from exc
    root = Path(output_root).expanduser().resolve()
    job = find_job(root, safe_id)
    if job is None:
        raise RevisionRunError(f"job not found: {safe_id}")
    approval = ApprovalStore(root).read(safe_id)
    if approval.get("state") != "needs_revision":
        raise RevisionRunError(
            f"job {safe_id} must be marked needs_revision before revision"
        )
    queue = RevisionQueue(root)
    try:
        task = queue.create(safe_id, note) if note is not None else queue.read(safe_id)
    except RevisionTaskError as exc:
        raise RevisionRunError(str(exc)) from exc
    if task is None:
        raise RevisionRunError(
            f"revision task is missing for job {safe_id}; create one or pass --note"
        )
    completed = _completed_result(root, task)
    if completed is not None:
        return completed
    if task.get("state") not in {"revision_queued", "revision_failed"}:
        raise RevisionRunError(f"revision task is not runnable: {task.get('state')}")

    revision_note = str(task.get("revision_note", "")).strip()
    if not revision_note:
        raise RevisionRunError("revision task has no revision note")
    revised_id = _revised_job_id(safe_id, revision_note)
    jobs_root = root / "jobs"
    jobs_root.mkdir(parents=True, exist_ok=True)
    destination = jobs_root / revised_id
    if not is_within(destination, root):
        raise RevisionRunError("revised job path escapes output root")
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{revised_id}.", dir=jobs_root))
    try:
        verdict = _verdict_from_job(job)
        localization = job.receipt.get("localization", {})
        resolved_locale = (
            localization.get("resolved_locale")
            if isinstance(localization, dict)
            else None
        ) or job.locale
        script = revise_script(
            _script_from_job(job, verdict, resolved_locale),
            revision_note,
            verdict.idea.name,
            resolved_locale,
        )
        (temporary_dir / "script.txt").write_text(script.as_text() + "\n", encoding="utf-8")
        CaptionAgent().generate_captions(script, temporary_dir / "captions.srt")
        ThumbnailAgent().create_thumbnail(
            verdict, temporary_dir / "thumbnail.jpg", locale=resolved_locale
        )
        VideoBuilder(Config(mode="mock", output_dir=root)).create_short(
            script, verdict, temporary_dir, locale=resolved_locale
        )

        created_at = utc_now_iso()
        revised_receipt = deepcopy(job.receipt)
        revised_receipt.update(
            {
                "job_id": revised_id,
                "created_at": created_at,
                "mode": "revision",
                "outputs": {
                    "script_txt": str(destination / "script.txt"),
                    "captions_srt": str(destination / "captions.srt"),
                    "thumbnail_jpg": str(destination / "thumbnail.jpg"),
                    "short_mp4": str(destination / "short.mp4"),
                    "revision_manifest_json": str(destination / MANIFEST_NAME),
                },
                "recording": {"enabled": False},
                "voiceover": {"status": "disabled"},
                "music": {"status": "disabled"},
                "queue": {"status": "disabled"},
                "scheduler": {"status": "disabled"},
                "publisher": {"status": "disabled"},
                "revision": {
                    "is_revision": True,
                    "original_job_id": safe_id,
                    "revision_note": revision_note,
                    "revision_strategy": "deterministic_local_rules",
                    "requires_reapproval": True,
                },
            }
        )
        (temporary_dir / "receipt.json").write_text(
            json.dumps(revised_receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest = build_revision_manifest(
            original_job_id=safe_id,
            revised_job_id=revised_id,
            revision_note=revision_note,
            revision_task_path=queue.task_path(safe_id),
            source_job_dir=job.job_dir,
            revised_job_dir=destination,
        )
        write_revision_manifest(temporary_dir / MANIFEST_NAME, manifest)

        approval_path = root / "approvals" / f"{revised_id}.json"
        if approval_path.exists():
            if not is_within(approval_path, root):
                raise RevisionRunError("revised approval path escapes output root")
            approval_path.unlink()
        _safe_replace_job(temporary_dir, destination, root, safe_id)
        queue.complete(task, revised_id)
    except Exception as exc:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        try:
            queue.fail(task, str(exc))
        except Exception:
            pass
        if isinstance(exc, RevisionRunError):
            raise
        raise RevisionRunError(f"revision failed for job {safe_id}: {exc}") from exc
    return RevisionResult(
        original_job_id=safe_id,
        revised_job_id=revised_id,
        revised_job_dir=destination,
        revision_note=revision_note,
        manifest=manifest,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic local revision for a Shorts Factory job."
    )
    parser.add_argument("--job-id", required=True, help="Original job ID to revise")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    parser.add_argument(
        "--note",
        default=None,
        help="Create or update the local revision task with this human note",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_revision(args.job_id, args.output_root, args.note)
    except (RevisionRunError, OSError) as exc:
        print(f"Revision refused: {exc}", file=sys.stderr)
        return 1
    print(f"Revision created: {result.revised_job_dir}")
    print(f"Original job: {result.original_job_id}")
    print(f"Revision note: {result.revision_note}")
    print("Reapproval required. Publishing status: not_published.")
    return 0
