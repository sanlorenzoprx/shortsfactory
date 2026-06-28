from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from content_factory.exporting.manifest import read_export_manifest
from content_factory.mission_control.approvals import ApprovalStore, validate_job_id
from content_factory.mission_control.job_index import JobRecord, find_job, is_within

from .quality_model import SCORING_VERSION, QualityIssue, issue, weighted_score
from .quality_store import QualityStore, QualityStoreError


class QualityScoringError(RuntimeError):
    """A safe, user-facing scoring refusal."""


PLACEHOLDER_PATTERN = re.compile(
    r"\b(todo|placeholder|lorem ipsum|fake path)\b|\{\{|\$\{|[A-Za-z]:\\(?:tmp|path)\\|/tmp/",
    re.IGNORECASE,
)
TIMESTAMP_PATTERN = re.compile(
    r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}"
)
INDEX_PATTERN = re.compile(r"(?m)^\s*\d+\s*$")
HOOK_SIGNALS = (
    "test",
    "score",
    "verdict",
    "risk",
    "before",
    "stop",
    "build",
    "idea",
    "ghost town",
    "prueba",
    "puntuación",
    "veredicto",
    "riesgo",
)
CTA_SIGNALS = (
    "try",
    "test",
    "run",
    "score",
    "enter",
    "start",
    "review",
    "build",
    "save",
    "share",
    "prueba",
    "probar",
    "revisa",
    "empieza",
    "construir",
)


def _clamp(value: int) -> int:
    return max(0, min(100, round(value)))


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _script_lines(job: JobRecord) -> tuple[str, list[str]]:
    text = _read_text(job.artifacts.get("script.txt"))
    return text, [line.strip() for line in text.splitlines() if line.strip()]


def _hook_score(lines: list[str]) -> tuple[int, list[QualityIssue]]:
    if not lines:
        return 0, [issue("error", "hook", "Script has no hook.", "Add one short first line that creates curiosity or builder relevance.")]
    hook = lines[0]
    score = 50
    issues: list[QualityIssue] = []
    if len(hook) <= 90:
        score += 25
    elif len(hook) <= 140:
        score += 10
        issues.append(issue("warning", "hook", "Hook is longer than ideal for short-form video.", "Trim the first line to 90 characters or fewer."))
    else:
        score -= 15
        issues.append(issue("warning", "hook", "Hook is too long for a fast opening.", "Rewrite the first line as one concise claim or question."))
    lowered = hook.casefold()
    if any(signal in lowered for signal in HOOK_SIGNALS):
        score += 25
    else:
        issues.append(issue("warning", "hook", "Hook is present but lacks a strong curiosity, score, risk, or builder signal.", "Lead with the test, score, risk, verdict, or a direct builder consequence."))
    if lowered.startswith(("in this video", "today i", "hello", "welcome", "so,")):
        score -= 20
        issues.append(issue("warning", "hook", "Hook starts slowly.", "Remove the introduction and begin with the result or tension."))
    return _clamp(score), issues


def _clarity_score(text: str, lines: list[str]) -> tuple[int, list[QualityIssue]]:
    if not lines:
        return 0, [issue("error", "clarity", "Script is missing or empty.", "Generate a complete script with 3 to 8 meaningful lines.")]
    issues: list[QualityIssue] = []
    score = 35
    if 3 <= len(lines) <= 8:
        score += 30
    elif len(lines) < 3:
        score += 5
        issues.append(issue("warning", "clarity", "Script is too short to explain the result clearly.", "Add the score, risk, reason, and next action."))
    else:
        score += 10
        issues.append(issue("warning", "clarity", "Script has more than 8 meaningful lines.", "Remove secondary details and keep one idea per line."))
    lowered = text.casefold()
    if any(token in lowered for token in ("score", "risk", "verdict", "idea", "outcome", "puntuación", "riesgo", "veredicto")):
        score += 20
    else:
        issues.append(issue("warning", "clarity", "Script does not clearly name a score, risk, verdict, idea, or outcome.", "Add one concrete result signal."))
    if all(len(line) <= 140 for line in lines):
        score += 15
    else:
        issues.append(issue("warning", "clarity", "One or more script lines are difficult to scan.", "Split lines longer than 140 characters."))
    if PLACEHOLDER_PATTERN.search(text):
        score = min(score, 20)
        issues.append(issue("error", "clarity", "Script contains placeholder or fake-path content.", "Replace every placeholder with final audience-facing copy."))
    return _clamp(score), issues


def _cta_score(lines: list[str]) -> tuple[int, list[QualityIssue]]:
    if not lines:
        return 0, [issue("error", "cta", "CTA cannot be evaluated because the script is missing.", "Add a final line asking for one specific action.")]
    final_line = lines[-1]
    nearby = " ".join(lines[-2:]).casefold()
    issues: list[QualityIssue] = []
    score = 20
    if any(signal in nearby for signal in CTA_SIGNALS):
        score += 60
    else:
        issues.append(issue("warning", "cta", "No clear action appears near the end of the script.", "Make the final line ask for one specific action such as test, try, review, or start."))
    if len(final_line) <= 100:
        score += 15
    else:
        issues.append(issue("warning", "cta", "CTA is too long.", "Shorten the final action to 100 characters or fewer."))
    if any(token in final_line.casefold() for token in ("now", "first", "before", "ahora", "primero", "antes")):
        score += 5
    return _clamp(score), issues


def _word_set(value: str) -> set[str]:
    return {word for word in re.findall(r"[\wÀ-ÿ]+", value.casefold()) if len(word) > 2}


def _captions_score(script_text: str, captions_text: str) -> tuple[int, list[QualityIssue]]:
    if not captions_text.strip():
        return 0, [issue("warning", "captions", "Captions are missing or empty.", "Generate captions.srt from the final script.")]
    issues: list[QualityIssue] = []
    score = 20
    if INDEX_PATTERN.search(captions_text):
        score += 20
    else:
        issues.append(issue("warning", "captions", "Captions do not contain valid-looking SRT indices.", "Regenerate captions with sequential numeric blocks."))
    if TIMESTAMP_PATTERN.search(captions_text):
        score += 30
    else:
        issues.append(issue("warning", "captions", "Captions do not contain valid-looking SRT timestamps.", "Regenerate captions with start and end timestamps."))
    script_words = _word_set(script_text)
    caption_words = _word_set(captions_text)
    overlap = len(script_words & caption_words) / max(len(script_words), 1)
    if script_words and overlap >= 0.5:
        score += 30
    else:
        issues.append(issue("warning", "captions", "Caption text does not closely match the script.", "Regenerate captions from the current script.txt."))
    if PLACEHOLDER_PATTERN.search(captions_text):
        score = min(score, 20)
        issues.append(issue("error", "captions", "Captions contain placeholder or fake-path content.", "Replace placeholder text and regenerate captions."))
    return _clamp(score), issues


def _metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _requested(metadata: dict[str, Any]) -> bool:
    return metadata.get("enabled") is True or metadata.get("status") not in (None, "disabled")


def _media_score(job: JobRecord) -> tuple[int, list[QualityIssue], bool, bool]:
    video_names = ("final.mp4", "short_with_music.mp4", "short_with_voice.mp4", "short.mp4")
    video = next((job.artifacts[name] for name in video_names if name in job.artifacts), None)
    thumbnail = job.artifacts.get("thumbnail.jpg")
    has_video = video is not None and video.is_file() and video.stat().st_size > 0
    has_thumbnail = thumbnail is not None and thumbnail.is_file() and thumbnail.stat().st_size > 0
    issues: list[QualityIssue] = []
    score = 0
    if has_video:
        score += 60
    else:
        issues.append(issue("error", "media", "No usable MP4 video is available.", "Regenerate the job video before review or export."))
    if has_thumbnail:
        score += 30
    else:
        issues.append(issue("warning", "media", "Thumbnail is missing or empty.", "Regenerate thumbnail.jpg."))
    recording = _metadata(job.receipt.get("recording"))
    if recording.get("enabled") is True:
        if "app_recording.mp4" in job.artifacts:
            score += 10
        else:
            issues.append(issue("warning", "media", "Receipt says recording was requested, but app_recording.mp4 is missing.", "Re-run the controlled recording step or clear the stale receipt claim."))
    else:
        score += 10
    return _clamp(score), issues, has_video, has_thumbnail


def _audio_score(job: JobRecord) -> tuple[int, list[QualityIssue]]:
    voiceover = _metadata(job.receipt.get("voiceover"))
    music = _metadata(job.receipt.get("music"))
    voice_requested = _requested(voiceover)
    music_requested = _requested(music)
    issues: list[QualityIssue] = []
    if not voice_requested and not music_requested:
        return 80, issues
    score = 0
    if voice_requested:
        if "short_with_voice.mp4" in job.artifacts or "short_with_music.mp4" in job.artifacts:
            score += 50 if not music_requested else 40
        else:
            issues.append(issue("error", "audio", "Voiceover was requested but no voice-mixed video is available.", "Regenerate the voiceover mix or correct the receipt metadata."))
    if music_requested:
        if "short_with_music.mp4" in job.artifacts:
            score += 50 if not voice_requested else 40
        else:
            issues.append(issue("error", "audio", "Music was requested but no final music-mixed video is available.", "Regenerate the music mix or correct the receipt metadata."))
    if voice_requested and music_requested and "short_with_music.mp4" in job.artifacts:
        score += 20
    audio_warnings = [
        warning
        for warning in job.warnings
        if any(token in warning.casefold() for token in ("audio", "voice", "music", "tts"))
    ]
    if audio_warnings:
        score -= min(30, len(audio_warnings) * 10)
        issues.append(issue("warning", "audio", "Receipt contains audio-generation warnings.", "Inspect the audio warnings and listen to the final video before approval."))
    return _clamp(score), issues


def _localization_score(job: JobRecord, script: str, captions: str) -> tuple[int, list[QualityIssue]]:
    locale = job.locale
    issues: list[QualityIssue] = []
    if locale in ("", "unknown"):
        return 20, [issue("warning", "localization", "Receipt does not identify a locale.", "Record the resolved locale in receipt.json.")]
    if locale == "es-PR":
        text = f"{script}\n{captions}".casefold()
        signals = ("prueba", "puntuación", "riesgo", "veredicto", "esta idea", "antes de construir")
        matches = sum(signal in text for signal in signals)
        if matches >= 2:
            return 100, issues
        issues.append(issue("warning", "localization", "es-PR job lacks expected Spanish phrases in script or captions.", "Regenerate localized script and captions using the es-PR catalog."))
        return 45, issues
    if locale == "en-US":
        return 100, issues
    warning_text = " ".join(job.warnings).casefold()
    if "fallback" in warning_text or "unsupported" in warning_text:
        issues.append(issue("warning", "localization", f"Locale {locale} used a recorded fallback.", "Review the fallback language before approval."))
        return 75, issues
    issues.append(issue("error", "localization", f"Unsupported locale {locale} has no recorded fallback warning.", "Use a supported locale or record the localization fallback."))
    return 30, issues


def _receipt_score(job: JobRecord) -> tuple[int, list[QualityIssue]]:
    receipt = job.receipt
    if not receipt:
        return 0, [issue("error", "receipt", "receipt.json is invalid or not a JSON object.", "Regenerate a valid receipt before review.")]
    required = ("job_id", "created_at", "locale", "mode", "idea", "verdict", "outputs", "warnings")
    missing = [name for name in required if name not in receipt]
    score = 100 - len(missing) * 10
    issues: list[QualityIssue] = []
    if missing:
        severity = "error" if any(name in missing for name in ("job_id", "created_at", "locale")) else "warning"
        issues.append(issue(severity, "receipt", f"Receipt is missing required fields: {', '.join(missing)}.", "Regenerate receipt.json with the complete job schema."))
    if "REVISION_MANIFEST.json" in job.artifacts:
        revision = receipt.get("revision")
        if not isinstance(revision, dict) or revision.get("requires_reapproval") is not True:
            score = min(score, 30)
            issues.append(issue("error", "receipt", "Revised job receipt is missing required revision lineage.", "Restore revision metadata with original job ID and reapproval requirement."))
    critical = [warning for warning in job.warnings if any(token in warning.casefold() for token in ("failed", "error", "missing"))]
    if critical:
        score -= min(30, len(critical) * 10)
        issues.append(issue("warning", "receipt", "Receipt contains generation failure warnings.", "Inspect and resolve generation warnings before approval."))
    return _clamp(score), issues


def _live_enabled(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"live_publish_enabled", "live_publishing_enabled"} and child is True:
                return True
            if _live_enabled(child):
                return True
    elif isinstance(value, list):
        return any(_live_enabled(child) for child in value)
    return False


def _publisher_score(job: JobRecord) -> tuple[int, list[QualityIssue]]:
    publisher = _metadata(job.receipt.get("publisher"))
    claimed = publisher.get("status") not in (None, "disabled") or bool(publisher.get("publisher_plan"))
    path = job.artifacts.get("publisher_package.json")
    if path is None:
        if claimed:
            return 0, [
                issue(
                    "error",
                    "publisher_package",
                    "Receipt claims a publisher package, but none is available.",
                    "Regenerate the dry-run publisher package or correct the receipt.",
                )
            ]
        return 80, []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 20, [
            issue(
                "error",
                "publisher_package",
                "Publisher package JSON is invalid.",
                "Regenerate the local dry-run publisher package.",
            )
        ]
    if _live_enabled(value):
        return 0, [
            issue(
                "error",
                "publisher_package",
                "Publisher package enables live publishing.",
                "Disable live publishing and regenerate a dry-run-only package.",
            )
        ]
    return 100, []


def _present_and_missing(job: JobRecord, has_video: bool, has_thumbnail: bool) -> tuple[list[str], list[str]]:
    present = sorted(job.artifacts)
    missing: list[str] = []
    if not has_video:
        missing.append("video.mp4")
    if not has_thumbnail:
        missing.append("thumbnail.jpg")
    for name in ("script.txt", "captions.srt", "receipt.json"):
        if name not in job.artifacts:
            missing.append(name)
    publisher = _metadata(job.receipt.get("publisher"))
    if publisher.get("status") not in (None, "disabled") and "publisher_package.json" not in job.artifacts:
        missing.append("publisher_package.json")
    return present, missing


def evaluate_job(
    job_id: str,
    output_root: str | Path = "output",
) -> dict[str, Any]:
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise QualityScoringError("invalid job_id") from exc
    root = Path(output_root).expanduser().resolve()
    job = find_job(root, safe_id)
    if job is None:
        raise QualityScoringError(f"job not found: {safe_id}")
    script_text, lines = _script_lines(job)
    captions_text = _read_text(job.artifacts.get("captions.srt"))
    category_scores: dict[str, int] = {}
    issues: list[QualityIssue] = []

    category_scores["hook"], found = _hook_score(lines)
    issues.extend(found)
    category_scores["clarity"], found = _clarity_score(script_text, lines)
    issues.extend(found)
    category_scores["cta"], found = _cta_score(lines)
    issues.extend(found)
    category_scores["captions"], found = _captions_score(script_text, captions_text)
    issues.extend(found)
    category_scores["media"], found, has_video, has_thumbnail = _media_score(job)
    issues.extend(found)
    category_scores["audio"], found = _audio_score(job)
    issues.extend(found)
    category_scores["localization"], found = _localization_score(job, script_text, captions_text)
    issues.extend(found)
    category_scores["receipt"], found = _receipt_score(job)
    issues.extend(found)
    category_scores["publisher_package"], found = _publisher_score(job)
    issues.extend(found)

    overall = weighted_score(category_scores)
    has_error = any(found.severity == "error" for found in issues)
    status = "fail" if overall < 60 or has_error else "pass" if overall >= 80 else "warn"
    approval_ready = status == "pass" and not has_error and has_video
    approval_store = ApprovalStore(root)
    approval = approval_store.read(safe_id)
    approval_path = root / "approvals" / f"{safe_id}.json"
    has_approval = approval_path.is_file() and is_within(approval_path, root)
    export_root = root.parent / "exports"
    try:
        export_manifest = read_export_manifest(export_root, safe_id)
    except ValueError:
        export_manifest = None
    export_ready = approval_ready and approval.get("state") == "approved"
    core_missing = not has_video or "script.txt" not in job.artifacts or not job.receipt
    if export_ready:
        recommended_action = "export"
    elif approval.get("state") == "needs_revision":
        recommended_action = "revise"
    elif status == "pass" and approval_ready:
        recommended_action = "approve"
    elif status == "warn":
        recommended_action = "revise"
    elif status == "fail" and core_missing:
        recommended_action = "reject"
    else:
        recommended_action = "inspect"
    present, missing = _present_and_missing(job, has_video, has_thumbnail)
    checks = {
        "has_video": has_video,
        "has_thumbnail": has_thumbnail,
        "has_script": "script.txt" in job.artifacts and bool(script_text.strip()),
        "has_captions": "captions.srt" in job.artifacts and bool(captions_text.strip()),
        "has_receipt": bool(job.receipt),
        "has_audio_metadata": isinstance(job.receipt.get("voiceover"), dict) or isinstance(job.receipt.get("music"), dict),
        "has_publisher_package": "publisher_package.json" in job.artifacts,
        "has_approval": has_approval,
        "has_export_manifest": export_manifest is not None,
    }
    return {
        "job_id": safe_id,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "overall_score": overall,
        "status": status,
        "approval_ready": approval_ready,
        "export_ready": export_ready,
        "recommended_action": recommended_action,
        "category_scores": category_scores,
        "issues": [found.to_dict() for found in issues],
        "missing_artifacts": missing,
        "present_artifacts": present,
        "checks": checks,
        "scoring_version": SCORING_VERSION,
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
    }


def score_job(job_id: str, output_root: str | Path = "output") -> dict[str, Any]:
    report = evaluate_job(job_id, output_root)
    try:
        QualityStore(output_root).write(report)
    except QualityStoreError as exc:
        raise QualityScoringError(str(exc)) from exc
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute a deterministic local quality score for a Shorts Factory job."
    )
    parser.add_argument("--job-id", required=True, help="Job ID to score")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    parser.add_argument("--json", action="store_true", help="Print the complete report JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = score_job(args.job_id, args.output_root)
    except (QualityScoringError, OSError) as exc:
        print(f"Scoring refused: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Quality report written: {Path(args.output_root).resolve() / 'quality' / (args.job_id + '.json')}")
        print(f"Overall score: {report['overall_score']} ({report['status']})")
        print(f"Recommended action: {report['recommended_action']}")
        print("Publishing status: not_published (live publishing disabled)")
    return 0
