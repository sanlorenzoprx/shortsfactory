from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import uuid4

from content_factory.mission_control.job_index import is_within

from .youtube_metadata import YouTubeMetadataError, YouTubeUploadMetadataV1, read_metadata_json
from .youtube_credentials import DEFAULT_RECEIPT, GoogleYouTubeOAuthBackend
from .youtube_publisher import (
    GoogleApiYouTubeUploadTransport,
    YouTubeCredentials,
    YouTubePublisherError,
    YouTubeUploadPayloadBuilder,
    YouTubeUploadTransport,
)


EXPECTED_CHANNEL_ID = "UCIzMYpBt3WdSXZBrvoE7eCg"
RECEIPT_VERSION = "phase5b.2.supervised-youtube-upload.v1"
REQUIRED_VERDICT_FIELDS = (
    "verdict_headline",
    "lit_score",
    "risk_level",
    "top_reason",
    "next_step",
)
URL_PATTERN = re.compile(r"https?://\S+", re.I)
SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|authorization|bearer|auth[_ -]?code)"
    r"\s*[:=]\s*[^\s,;]+"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc


def _redact_error(exc: BaseException, secrets: Sequence[str] = ()) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = URL_PATTERN.sub("[REDACTED_URL]", text)
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:500]


def _atomic_json_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite upload receipt: {path.name}")
    descriptor, name = tempfile.mkstemp(prefix=".youtube-supervised.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class SupervisedUploadResult:
    classification: str
    attempt_id: str
    receipt_paths: tuple[str, ...]
    video_id: str | None = None
    video_url: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.classification == "successful_live_upload"


class SupervisedUploadReceiptStore:
    def __init__(self, output_root: str | Path = "output"):
        self.root = Path(output_root).expanduser().resolve() / "youtube" / "supervised_uploads"

    def new_attempt_id(self, now: datetime) -> str:
        return f"ytu_{now.astimezone(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}_{uuid4().hex[:8]}"

    def write(self, attempt_id: str, sequence: int, classification: str, receipt: dict[str, Any]) -> Path:
        if Path(attempt_id).name != attempt_id or not attempt_id.startswith("ytu_"):
            raise ValueError("invalid supervised upload attempt id")
        attempt_dir = (self.root / attempt_id).resolve()
        if not is_within(attempt_dir, self.root):
            raise ValueError("supervised upload receipt path escapes output root")
        path = attempt_dir / f"{sequence:02d}_{classification}.json"
        _atomic_json_new(path, receipt)
        return path


class SupervisedYouTubeUploadGate:
    """One-shot human-approved YouTube upload path, separate from batch autopilot."""

    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        preflight_receipt: str | Path = DEFAULT_RECEIPT,
        transport: YouTubeUploadTransport | None = None,
        credential_loader: Callable[[Path], YouTubeCredentials] | None = None,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.preflight_receipt = Path(preflight_receipt).expanduser().resolve()
        self.transport = transport or GoogleApiYouTubeUploadTransport()
        self.credential_loader = credential_loader or self._load_credentials
        self.now = now
        self.payload_builder = YouTubeUploadPayloadBuilder(now=now)
        self.receipts = SupervisedUploadReceiptStore(self.output_root)

    def run(
        self,
        *,
        videos: Sequence[str | Path],
        metadata_path: str | Path,
        confirm_channel_id: str,
        confirm_live_upload: bool,
        confirm_quota_reviewed: bool,
        confirm_policy_reviewed: bool,
    ) -> SupervisedUploadResult:
        started = self.now().astimezone(timezone.utc)
        attempt_id = self.receipts.new_attempt_id(started)
        receipt_paths: list[str] = []
        gates: list[dict[str, Any]] = []
        preflight: dict[str, Any] = {}
        channel: dict[str, Any] = {"id": None, "title": None}
        selected_video: Path | None = None
        metadata: dict[str, Any] = {}
        sources: dict[str, str | None] = {
            "credential_preflight": str(self.preflight_receipt),
            "generation_content_receipt": None,
            "autopilot_receipt": None,
            "lit_verdict_receipt": None,
            "quality_gate_receipt": None,
            "compliance_gate_receipt": None,
        }

        def check(name: str, passed: bool, detail: str) -> None:
            gates.append({"name": name, "passed": passed, "detail": detail})

        def block(classification: str, reason: str) -> SupervisedUploadResult:
            receipt = self._receipt(
                classification=classification,
                attempt_id=attempt_id,
                timestamp=self.now(),
                channel=channel,
                selected_video=selected_video,
                metadata_path=Path(metadata_path),
                metadata=metadata,
                sources=sources,
                gates=gates,
                upload_attempted=False,
                videos_insert_called=False,
                error=reason,
            )
            path = self.receipts.write(attempt_id, 1, classification, receipt)
            return SupervisedUploadResult(classification, attempt_id, (str(path),))

        approvals = {
            "confirm_live_upload": confirm_live_upload,
            "confirm_quota_reviewed": confirm_quota_reviewed,
            "confirm_policy_reviewed": confirm_policy_reviewed,
        }
        for name, passed in approvals.items():
            check(name, passed is True, "explicit CLI approval is required")
        missing = [name for name, passed in approvals.items() if passed is not True]
        if missing:
            return block("blocked_missing_approval", "missing explicit approval: " + ", ".join(missing))

        try:
            raw_preflight = _read_json(self.preflight_receipt, "YouTube credential preflight receipt")
            if not isinstance(raw_preflight, dict):
                raise ValueError("YouTube credential preflight receipt must contain an object")
            preflight = raw_preflight
            channel_value = preflight.get("channel")
            token = preflight.get("token")
            safety = preflight.get("safety")
            checks = preflight.get("checks")
            if not isinstance(channel_value, dict) or not isinstance(token, dict) or not isinstance(safety, dict):
                raise ValueError("YouTube credential preflight receipt is incomplete")
            channel = {"id": channel_value.get("id"), "title": channel_value.get("title")}
            check("preflight_status", preflight.get("status") == "passed", "preflight status must be passed")
            check("channel_identity", channel_value.get("status") == "verified", "channel identity must be verified")
            check("youtube_upload_scope", token.get("youtube_upload_scope") is True, "youtube.upload scope is required")
            check("youtube_readonly_scope", token.get("youtube_readonly_scope") is True, "youtube.readonly scope is required")
            check("preflight_upload_not_attempted", safety.get("upload_attempted") is False, "preflight must precede upload")
            check("preflight_videos_insert_not_called", safety.get("videos_insert_called") is False, "preflight must not call videos.insert")
            check("preflight_secrets_not_recorded", safety.get("secrets_recorded") is False, "preflight must be redacted")
            named_checks = {
                row.get("name"): row.get("passed")
                for row in checks if isinstance(row, dict)
            } if isinstance(checks, list) else {}
            check("preflight_channel_check", named_checks.get("channel_identity") is True, "channel preflight check must pass")
            if any(row["passed"] is not True for row in gates[-8:]):
                raise ValueError("YouTube credential preflight receipt did not pass every required safety check")
        except (ValueError, OSError) as exc:
            return block("blocked_missing_preflight", str(exc))

        channel_matches = (
            channel.get("id") == EXPECTED_CHANNEL_ID
            and confirm_channel_id == EXPECTED_CHANNEL_ID
            and confirm_channel_id == channel.get("id")
        )
        check("exact_channel_id", channel_matches, f"confirmed channel must be {EXPECTED_CHANNEL_ID}")
        if not channel_matches:
            return block("blocked_channel_mismatch", "confirmed channel ID does not match Ghost Town Test")

        check("one_video_selected", len(videos) == 1, "exactly one video path is required")
        if len(videos) != 1:
            return block("blocked_missing_video", "exactly one video path is required; batch upload is refused")
        selected_video = Path(videos[0]).expanduser().resolve()
        check("video_is_file", selected_video.is_file(), "selected video must be a non-empty file")
        check("video_is_not_directory", not selected_video.is_dir(), "directory upload is refused")
        check("video_is_mp4", selected_video.suffix.casefold() == ".mp4", "selected video must be an MP4 artifact")
        if (
            not selected_video.is_file()
            or selected_video.stat().st_size == 0
            or selected_video.suffix.casefold() != ".mp4"
        ):
            return block("blocked_missing_video", "selected video is missing, empty, a directory, or not an MP4")

        try:
            trust = self._validate_source_chain(selected_video, Path(metadata_path).expanduser().resolve())
            sources.update(trust["sources"])
            metadata = trust["metadata"]
            for result in trust["gates"]:
                gates.append(result)
        except SourceChainError as exc:
            if exc.sources:
                sources.update(exc.sources)
            classification = exc.classification
            check(exc.gate_name, False, str(exc))
            return block(classification, str(exc))

        try:
            self._validate_metadata(metadata, selected_video, Path(metadata_path).expanduser().resolve())
            payload = self.payload_builder.build(
                Path(metadata_path).expanduser().resolve(),
                expected_job_id=metadata["source_job_id"],
                require_embedded_approval=False,
            )
            if Path(payload.video_path).resolve() != selected_video:
                raise YouTubePublisherError("metadata video does not match the explicitly selected video")
            check("upload_metadata", True, "YouTube metadata and payload passed validation")
        except (ValueError, YouTubePublisherError) as exc:
            check("upload_metadata", False, str(exc))
            return block("blocked_invalid_metadata", str(exc))

        try:
            token_path = self._preflight_token_path(preflight)
            credentials = self.credential_loader(token_path)
            credential_checks = credentials.checks(self.now().astimezone(timezone.utc))
            for result in credential_checks:
                check(result["name"], result["passed"] is True, "runtime OAuth credential check")
            if any(result["passed"] is not True for result in credential_checks):
                raise ValueError("runtime YouTube credentials no longer pass preflight")
        except Exception as exc:
            check("runtime_credentials", False, _redact_error(exc))
            return block("blocked_missing_preflight", _redact_error(exc))

        attempted = self._receipt(
            classification="attempted_live_upload",
            attempt_id=attempt_id,
            timestamp=self.now(),
            channel=channel,
            selected_video=selected_video,
            metadata_path=Path(metadata_path),
            metadata=metadata,
            sources=sources,
            gates=gates,
            upload_attempted=True,
            videos_insert_called=False,
            error=None,
        )
        attempted_path = self.receipts.write(attempt_id, 1, "attempted_live_upload", attempted)
        receipt_paths.append(str(attempted_path))

        try:
            response = self.transport.upload(access_token=credentials.access_token, payload=payload)
            video_id = response.get("id") if isinstance(response, dict) else None
            if not isinstance(video_id, str) or not video_id.strip():
                raise YouTubePublisherError("YouTube upload response is missing a video id")
        except Exception as exc:
            videos_insert_called = bool(getattr(self.transport, "videos_insert_called", True))
            failed = self._receipt(
                classification="failed_live_upload",
                attempt_id=attempt_id,
                timestamp=self.now(),
                channel=channel,
                selected_video=selected_video,
                metadata_path=Path(metadata_path),
                metadata=metadata,
                sources=sources,
                gates=gates,
                upload_attempted=True,
                videos_insert_called=videos_insert_called,
                error=_redact_error(exc, (credentials.access_token,)),
            )
            failed_path = self.receipts.write(attempt_id, 2, "failed_live_upload", failed)
            receipt_paths.append(str(failed_path))
            return SupervisedUploadResult("failed_live_upload", attempt_id, tuple(receipt_paths))

        video_id = video_id.strip()
        successful = self._receipt(
            classification="successful_live_upload",
            attempt_id=attempt_id,
            timestamp=self.now(),
            channel=channel,
            selected_video=selected_video,
            metadata_path=Path(metadata_path),
            metadata=metadata,
            sources=sources,
            gates=gates,
            upload_attempted=True,
            videos_insert_called=True,
            error=None,
            result={
                "video_id": video_id,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "privacy_status": payload.body["status"]["privacyStatus"],
            },
        )
        success_path = self.receipts.write(attempt_id, 2, "successful_live_upload", successful)
        receipt_paths.append(str(success_path))
        return SupervisedUploadResult(
            "successful_live_upload",
            attempt_id,
            tuple(receipt_paths),
            video_id,
            successful["result"]["video_url"],
        )

    def _validate_source_chain(self, video: Path, metadata_path: Path) -> dict[str, Any]:
        sources: dict[str, str | None] = {}
        jobs_root = (self.output_root / "jobs").resolve()
        if not is_within(video, jobs_root):
            raise SourceChainError(
                "blocked_untrusted_video",
                "video_inside_generated_jobs_root",
                "selected video is outside the configured generated jobs root",
                sources,
            )
        generation_receipt_path = video.parent / "receipt.json"
        sources["generation_content_receipt"] = str(generation_receipt_path)
        try:
            generation = _read_json(generation_receipt_path, "generation/content receipt")
        except ValueError as exc:
            raise SourceChainError("blocked_untrusted_video", "generation_content_receipt", str(exc), sources) from exc
        if not isinstance(generation, dict):
            raise SourceChainError("blocked_untrusted_video", "generation_content_receipt", "generation/content receipt must contain an object", sources)
        job_id = generation.get("job_id")
        if not isinstance(job_id, str) or not job_id or job_id != video.parent.name:
            raise SourceChainError("blocked_untrusted_video", "generation_content_receipt", "generation/content receipt does not match the selected video job", sources)
        outputs = generation.get("outputs")
        if not isinstance(outputs, dict) or not self._path_is_listed(video, outputs.values(), generation_receipt_path.parent):
            raise SourceChainError("blocked_untrusted_video", "video_bound_to_generation_receipt", "selected video is not listed by its generation/content receipt", sources)

        matches = []
        batches_root = self.output_root / "autopilot" / "batches"
        if batches_root.is_dir():
            for batch_dir in batches_root.iterdir():
                if not batch_dir.is_dir():
                    continue
                jobs_path = batch_dir / "generated_jobs.json"
                try:
                    jobs = _read_json(jobs_path, "generated jobs receipt")
                except ValueError:
                    continue
                if not isinstance(jobs, list):
                    continue
                for job in jobs:
                    if not isinstance(job, dict) or job.get("job_id") != job_id:
                        continue
                    if self._reference_matches(job.get("receipt_path"), generation_receipt_path, batch_dir):
                        matches.append((batch_dir, job))
        if len(matches) != 1:
            raise SourceChainError(
                "blocked_untrusted_video",
                "video_bound_to_autopilot_batch",
                "selected video must match exactly one generated job in a Phase 5A batch",
                sources,
            )
        batch_dir, job = matches[0]
        autopilot_receipt_path = batch_dir / "AUTOPILOT_RECEIPT.json"
        sources["autopilot_receipt"] = str(autopilot_receipt_path)
        try:
            autopilot_receipt = _read_json(autopilot_receipt_path, "autopilot receipt")
        except ValueError as exc:
            raise SourceChainError("blocked_untrusted_video", "autopilot_receipt", str(exc), sources) from exc
        if not isinstance(autopilot_receipt, dict) or autopilot_receipt.get("status") != "completed" or autopilot_receipt.get("mode") != "dry_run":
            raise SourceChainError("blocked_untrusted_video", "autopilot_receipt", "source autopilot batch must be a completed dry_run", sources)

        publisher_plan_path = self._resolve_reference(job.get("publisher_plan"), batch_dir)
        if (
            publisher_plan_path is None
            or not publisher_plan_path.is_file()
            or not is_within(publisher_plan_path, video.parent)
        ):
            raise SourceChainError("blocked_invalid_metadata", "publisher_plan", "generated publisher plan is missing", sources)
        try:
            publisher_plan = _read_json(publisher_plan_path, "publisher plan")
        except ValueError as exc:
            raise SourceChainError("blocked_invalid_metadata", "publisher_plan", str(exc), sources) from exc
        relative_metadata = publisher_plan.get("platforms", {}).get("youtube_shorts") if isinstance(publisher_plan, dict) and isinstance(publisher_plan.get("platforms"), dict) else None
        trusted_metadata_path = self._resolve_reference(relative_metadata, publisher_plan_path.parent)
        if (
            trusted_metadata_path != metadata_path.resolve()
            or not is_within(metadata_path, video.parent)
        ):
            raise SourceChainError("blocked_invalid_metadata", "metadata_bound_to_publisher_plan", "metadata is not the generated YouTube metadata referenced by the job publisher plan", sources)
        try:
            metadata_value, _ = read_metadata_json(metadata_path)
            metadata = YouTubeUploadMetadataV1.from_dict(
                metadata_value,
                allow_legacy=True,
                source_receipt_references={
                    key: value for key, value in sources.items() if isinstance(value, str)
                },
            ).to_dict()
        except YouTubeMetadataError as exc:
            raise SourceChainError("blocked_invalid_metadata", "upload_metadata", str(exc), sources) from exc
        if metadata.get("source_job_id") != job_id:
            raise SourceChainError("blocked_invalid_metadata", "metadata_job", "metadata does not match the selected video job", sources)

        idea_id = job.get("idea_id")
        lit_path = batch_dir / "lit_verdicts.json"
        sources["lit_verdict_receipt"] = str(lit_path)
        try:
            verdicts = _read_json(lit_path, "LIT verdict receipt")
        except ValueError as exc:
            raise SourceChainError("blocked_missing_lit_verdict", "lit_verdict", str(exc), sources) from exc
        verdict = next((row for row in verdicts if isinstance(row, dict) and row.get("idea_id") == idea_id), None) if isinstance(verdicts, list) else None
        verdict_value = verdict.get("verdict") if isinstance(verdict, dict) else None
        if not isinstance(verdict_value, dict) or any(verdict_value.get(name) in (None, "") for name in REQUIRED_VERDICT_FIELDS):
            raise SourceChainError("blocked_missing_lit_verdict", "lit_verdict", "matching complete LIT verdict receipt is missing or failed", sources)

        quality_path = batch_dir / "quality_gates.json"
        compliance_path = batch_dir / "compliance_gates.json"
        sources["quality_gate_receipt"] = str(quality_path)
        sources["compliance_gate_receipt"] = str(compliance_path)
        quality = self._passed_gate(quality_path, job_id, "quality")
        compliance = self._passed_gate(compliance_path, job_id, "compliance")
        if quality is None or compliance is None:
            raise SourceChainError(
                "blocked_missing_quality_gate",
                "quality_compliance_gates",
                "matching quality and compliance gate receipts must both pass",
                sources,
            )
        return {
            "metadata": metadata,
            "sources": sources,
            "gates": [
                {"name": "video_bound_to_generation_receipt", "passed": True, "detail": f"job_id={job_id}"},
                {"name": "video_bound_to_autopilot_batch", "passed": True, "detail": f"batch_id={batch_dir.name}"},
                {"name": "lit_verdict", "passed": True, "detail": "matching complete LIT verdict receipt passed"},
                {"name": "quality_gate", "passed": True, "detail": str(quality.get("reason", "quality gate passed"))},
                {"name": "compliance_gate", "passed": True, "detail": str(compliance.get("reason", "compliance gate passed"))},
            ],
        }

    def _passed_gate(self, path: Path, job_id: str, gate_name: str) -> dict[str, Any] | None:
        try:
            rows = _read_json(path, f"{gate_name} gate receipt")
        except ValueError:
            return None
        if not isinstance(rows, list):
            return None
        return next((
            row for row in rows
            if isinstance(row, dict)
            and row.get("job_id") == job_id
            and row.get("gate_name") == gate_name
            and row.get("status") == "pass"
            and row.get("blocking") is False
        ), None)

    def _validate_metadata(self, metadata: dict[str, Any], video: Path, metadata_path: Path) -> None:
        if metadata.get("platform") != "youtube_shorts":
            raise ValueError("metadata platform must be youtube_shorts")
        title = metadata.get("title")
        description = metadata.get("description")
        privacy = metadata.get("privacy_status")
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            raise ValueError("YouTube title must contain 1 to 100 characters")
        if not isinstance(description, str) or not description.strip() or len(description) > 5000:
            raise ValueError("YouTube description must contain 1 to 5000 characters")
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status must be explicitly private, unlisted, or public")
        if not isinstance(metadata.get("made_for_kids"), bool):
            raise ValueError("made_for_kids must be explicitly true or false")
        if (metadata.get("publish_at") is not None or metadata.get("schedule_window") is not None) and privacy != "private":
            raise ValueError("scheduled YouTube uploads must use private privacy_status")
        video_value = metadata.get("video")
        if not isinstance(video_value, str) or not video_value.strip():
            raise ValueError("metadata video path is required")
        if (metadata_path.parent / video_value).resolve() != video:
            raise ValueError("metadata video does not match the explicitly selected video")

    def _path_is_listed(self, target: Path, values: Any, anchor: Path) -> bool:
        return any(self._reference_matches(value, target, anchor) for value in values)

    def _reference_matches(self, value: Any, target: Path, anchor: Path) -> bool:
        resolved = self._resolve_reference(value, anchor)
        return resolved == target.resolve() if resolved is not None else False

    def _resolve_reference(self, value: Any, anchor: Path) -> Path | None:
        if not isinstance(value, str) or not value.strip():
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path.resolve()
        candidates = ((anchor / path).resolve(), (Path.cwd() / path).resolve())
        return next((candidate for candidate in candidates if candidate.exists()), candidates[0])

    @staticmethod
    def _preflight_token_path(preflight: dict[str, Any]) -> Path:
        paths = preflight.get("paths")
        token = paths.get("token") if isinstance(paths, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise ValueError("preflight receipt does not reference the authorized-user token")
        return Path(token).expanduser().resolve()

    @staticmethod
    def _load_credentials(token_path: Path) -> YouTubeCredentials:
        state = GoogleYouTubeOAuthBackend().inspect_token(token_path=token_path)
        access_token = str(getattr(state.credentials, "token", "") or "")
        return YouTubeCredentials(access_token=access_token, scopes=state.scopes, expires_at=state.expires_at)

    @staticmethod
    def _receipt(
        *,
        classification: str,
        attempt_id: str,
        timestamp: datetime,
        channel: dict[str, Any],
        selected_video: Path | None,
        metadata_path: Path,
        metadata: dict[str, Any],
        sources: dict[str, str | None],
        gates: list[dict[str, Any]],
        upload_attempted: bool,
        videos_insert_called: bool,
        error: str | None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        description = metadata.get("description")
        return {
            "receipt_version": RECEIPT_VERSION,
            "classification": classification,
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "attempt_id": attempt_id,
            "channel": {"id": channel.get("id"), "title": channel.get("title")},
            "selected_video_path": str(selected_video) if selected_video else None,
            "metadata_summary": {
                "metadata_path": str(metadata_path.expanduser().resolve()),
                "schema_version": metadata.get("schema_version"),
                "source_job_id": metadata.get("source_job_id"),
                "title": metadata.get("title"),
                "description_present": isinstance(description, str) and bool(description.strip()),
                "description_length": len(description) if isinstance(description, str) else 0,
                "privacy_status": metadata.get("privacy_status"),
                "made_for_kids": metadata.get("made_for_kids"),
                "publish_at": metadata.get("publish_at") or (
                    metadata.get("schedule_window", {}).get("publish_at")
                    if isinstance(metadata.get("schedule_window"), dict) else None
                ),
            },
            "source_receipt_references": sources,
            "gate_results": gates,
            "videos_insert_called": videos_insert_called,
            "upload_attempted": upload_attempted,
            "secrets_recorded": False,
            "error": error,
            "result": result,
        }


class SourceChainError(ValueError):
    def __init__(
        self,
        classification: str,
        gate_name: str,
        message: str,
        sources: dict[str, str | None] | None = None,
    ):
        super().__init__(message)
        self.classification = classification
        self.gate_name = gate_name
        self.sources = sources or {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Perform exactly one explicitly approved supervised YouTube upload."
    )
    parser.add_argument("--video", action="append", required=True, help="One generated video artifact; repeat is refused")
    parser.add_argument("--metadata", required=True, help="Generated YouTube metadata JSON for the selected job")
    parser.add_argument("--confirm-channel-id", required=True)
    parser.add_argument("--confirm-live-upload", action="store_true")
    parser.add_argument("--confirm-quota-reviewed", action="store_true")
    parser.add_argument("--confirm-policy-reviewed", action="store_true")
    parser.add_argument("--preflight-receipt", default=str(DEFAULT_RECEIPT))
    parser.add_argument("--output-root", default="output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gate = SupervisedYouTubeUploadGate(
        output_root=args.output_root,
        preflight_receipt=args.preflight_receipt,
    )
    result = gate.run(
        videos=args.video,
        metadata_path=args.metadata,
        confirm_channel_id=args.confirm_channel_id,
        confirm_live_upload=args.confirm_live_upload,
        confirm_quota_reviewed=args.confirm_quota_reviewed,
        confirm_policy_reviewed=args.confirm_policy_reviewed,
    )
    print(f"Supervised upload result: {result.classification}")
    for path in result.receipt_paths:
        print(f"Receipt: {path}")
    if result.video_url:
        print(f"YouTube video: {result.video_url}")
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
