from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from content_factory.mission_control.job_index import is_within

from .autopilot_config import AutopilotConfig
from .autopilot_models import PublishAttempt


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_ANALYTICS_READONLY_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
YOUTUBE_REQUIRED_SCOPES = (
    YOUTUBE_UPLOAD_SCOPE,
    YOUTUBE_READONLY_SCOPE,
)
RECEIPT_VERSION = "phase5b.youtube.v1"


class YouTubePublisherError(ValueError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise YouTubePublisherError(f"{label} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise YouTubePublisherError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class YouTubeCredentials:
    access_token: str = field(default="", repr=False)
    scopes: tuple[str, ...] = ()
    expires_at: str | None = None

    @classmethod
    def from_env(cls) -> "YouTubeCredentials":
        access_token = os.getenv("YOUTUBE_OAUTH_ACCESS_TOKEN", "").strip()
        scopes = tuple(
            scope for scope in os.getenv("YOUTUBE_OAUTH_SCOPES", "").replace(",", " ").split()
            if scope
        )
        expires_at = os.getenv("YOUTUBE_OAUTH_TOKEN_EXPIRES_AT") or None
        token_file = os.getenv("YOUTUBE_TOKEN_FILE", "").strip()
        if not access_token and token_file:
            path = Path(token_file).expanduser().resolve()
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise YouTubePublisherError("configured YouTube token file is missing or invalid") from exc
            if (
                not isinstance(value, dict)
                or value.get("type") == "service_account"
                or "private_key" in value
                or "client_email" in value
            ):
                raise YouTubePublisherError("YouTube token file must contain installed-app authorized-user credentials")
            access_token = str(value.get("token", "")).strip()
            raw_scopes = value.get("scopes", [])
            if isinstance(raw_scopes, list):
                scopes = tuple(str(scope) for scope in raw_scopes if scope)
            expires_at = str(value.get("expiry")) if value.get("expiry") else None
        return cls(
            access_token=access_token,
            scopes=scopes,
            expires_at=expires_at,
        )

    def checks(self, now: datetime) -> list[dict[str, Any]]:
        expiry_valid = False
        if self.expires_at:
            try:
                expiry_valid = _parse_datetime(self.expires_at, "OAuth token expiry") > now
            except YouTubePublisherError:
                expiry_valid = False
        return [
            {"name": "oauth_access_token", "passed": bool(self.access_token)},
            {"name": "youtube_upload_scope", "passed": YOUTUBE_UPLOAD_SCOPE in self.scopes},
            {"name": "youtube_readonly_scope", "passed": YOUTUBE_READONLY_SCOPE in self.scopes},
            {"name": "oauth_token_not_expired", "passed": expiry_valid},
        ]


@dataclass(frozen=True)
class YouTubeLivePolicy:
    live_publishing_enabled: bool = False
    youtube_publishing_enabled: bool = False
    quota_remaining: int = 0
    policy_acknowledged: bool = False
    emergency_stop: bool = False
    credential_preflight_ready: bool = False

    @classmethod
    def from_env(cls) -> "YouTubeLivePolicy":
        raw_quota = os.getenv("YOUTUBE_UPLOAD_QUOTA_REMAINING", "0").strip()
        try:
            quota = int(raw_quota)
        except ValueError:
            quota = 0
        preflight_ready = False
        receipt_value = os.getenv(
            "YOUTUBE_PREFLIGHT_RECEIPT",
            "output/youtube/credential_preflight/YOUTUBE_CREDENTIAL_PREFLIGHT.json",
        ).strip()
        if receipt_value:
            try:
                receipt = json.loads(Path(receipt_value).expanduser().resolve().read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                receipt = {}
            readiness = receipt.get("readiness", {}) if isinstance(receipt, dict) else {}
            channel = receipt.get("channel", {}) if isinstance(receipt, dict) else {}
            token = receipt.get("token", {}) if isinstance(receipt, dict) else {}
            preflight_ready = (
                receipt.get("status") == "passed"
                and isinstance(readiness, dict)
                and readiness.get("ready_for_future_supervised_upload") is True
                and isinstance(channel, dict)
                and channel.get("status") == "verified"
                and isinstance(token, dict)
                and token.get("youtube_upload_scope") is True
                and token.get("youtube_readonly_scope") is True
            )
        return cls(
            live_publishing_enabled=_env_bool("LIVE_PUBLISHING_ENABLED"),
            youtube_publishing_enabled=_env_bool("YOUTUBE_PUBLISHING_ENABLED"),
            quota_remaining=max(0, quota),
            policy_acknowledged=_env_bool("YOUTUBE_POLICY_ACKNOWLEDGED"),
            emergency_stop=_env_bool("AUTOPILOT_EMERGENCY_STOP"),
            credential_preflight_ready=preflight_ready,
        )


@dataclass(frozen=True)
class YouTubeUploadPayload:
    metadata_path: str
    video_path: str
    parts: tuple[str, ...]
    body: dict[str, Any]
    notify_subscribers: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class YouTubeUploadTransport(Protocol):
    name: str

    def upload(
        self,
        *,
        access_token: str,
        payload: YouTubeUploadPayload,
    ) -> dict[str, Any]: ...


class GoogleApiYouTubeUploadTransport:
    """Official videos.insert transport. Imports remain optional until live setup."""

    name = "google_api_python_client"

    def __init__(self) -> None:
        self.videos_insert_called = False

    def upload(
        self,
        *,
        access_token: str,
        payload: YouTubeUploadPayload,
    ) -> dict[str, Any]:
        self.videos_insert_called = False
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise YouTubePublisherError(
                "The optional google-api-python-client and google-auth packages are required for a real YouTube upload."
            ) from exc

        credentials = Credentials(token=access_token, scopes=list(YOUTUBE_REQUIRED_SCOPES))
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        request = service.videos().insert(
            part=",".join(payload.parts),
            body=payload.body,
            notifySubscribers=payload.notify_subscribers,
            media_body=MediaFileUpload(payload.video_path, mimetype="video/mp4", resumable=True),
        )
        self.videos_insert_called = True
        response = None
        while response is None:
            _, response = request.next_chunk()
        if not isinstance(response, dict):
            raise YouTubePublisherError("YouTube returned an invalid upload response")
        return response


class YouTubeUploadPayloadBuilder:
    def __init__(self, *, now: Callable[[], datetime] = _utc_now):
        self.now = now

    def build(
        self,
        metadata_path: str | Path,
        *,
        expected_job_id: str,
        require_embedded_approval: bool = True,
    ) -> YouTubeUploadPayload:
        requested = Path(metadata_path).expanduser().resolve()
        source = self._read_json(requested, "publisher metadata")
        metadata_file, metadata, job_root = self._resolve_metadata(requested, source)

        if metadata.get("platform") != "youtube_shorts":
            raise YouTubePublisherError("publisher metadata is not for youtube_shorts")
        if metadata.get("source_job_id") != expected_job_id:
            raise YouTubePublisherError("publisher metadata job does not match publish attempt")
        if require_embedded_approval:
            if metadata.get("live_publish_enabled") is not True:
                raise YouTubePublisherError("publisher metadata does not explicitly enable live publishing")
            if metadata.get("approved_for_live_publish") is not True:
                raise YouTubePublisherError("publisher metadata is not approved for live publishing")

        title = metadata.get("title")
        description = metadata.get("description")
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            raise YouTubePublisherError("YouTube title must contain 1 to 100 characters")
        if not isinstance(description, str) or len(description) > 5000:
            raise YouTubePublisherError("YouTube description must contain at most 5000 characters")
        if not isinstance(metadata.get("made_for_kids"), bool):
            raise YouTubePublisherError("made_for_kids must be explicitly true or false")

        video_value = metadata.get("video")
        if not isinstance(video_value, str) or not video_value.strip():
            raise YouTubePublisherError("YouTube video path is required")
        video_path = (metadata_file.parent / video_value).resolve()
        if not is_within(video_path, job_root):
            raise YouTubePublisherError("YouTube video path escapes its job directory")
        if not video_path.is_file() or video_path.stat().st_size == 0:
            raise YouTubePublisherError("YouTube video is missing or empty")

        hashtags = metadata.get("hashtags", [])
        if not isinstance(hashtags, list) or any(not isinstance(value, str) for value in hashtags):
            raise YouTubePublisherError("YouTube hashtags must be a list of strings")
        raw_tags = metadata.get("tags", hashtags)
        if not isinstance(raw_tags, list) or any(not isinstance(value, str) for value in raw_tags):
            raise YouTubePublisherError("YouTube tags must be a list of strings")
        tags = [value.lstrip("#").strip() for value in raw_tags if value.lstrip("#").strip()]
        if sum(len(value) for value in tags) > 500:
            raise YouTubePublisherError("YouTube tags exceed the metadata limit")

        category_id = str(metadata.get("category_id", "22"))
        if not category_id.isdigit():
            raise YouTubePublisherError("YouTube category_id must be numeric")
        privacy_status = str(metadata.get("privacy_status", "private"))
        if privacy_status not in {"private", "unlisted", "public"}:
            raise YouTubePublisherError("YouTube privacy_status is invalid")

        status: dict[str, Any] = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": metadata["made_for_kids"],
        }
        publish_at = self._publish_at(metadata)
        if publish_at is not None:
            if privacy_status != "private":
                raise YouTubePublisherError("scheduled YouTube uploads must use private privacy_status")
            status["publishAt"] = publish_at

        snippet: dict[str, Any] = {
            "title": title.strip(),
            "description": description,
            "categoryId": category_id,
        }
        if tags:
            snippet["tags"] = tags
        locale = metadata.get("locale")
        if isinstance(locale, str) and locale.strip():
            snippet["defaultLanguage"] = locale.strip()

        notify = metadata.get("notify_subscribers", False)
        if not isinstance(notify, bool):
            raise YouTubePublisherError("notify_subscribers must be boolean")
        return YouTubeUploadPayload(
            metadata_path=str(metadata_file),
            video_path=str(video_path),
            parts=("snippet", "status"),
            body={"snippet": snippet, "status": status},
            notify_subscribers=notify,
        )

    def _publish_at(self, metadata: dict[str, Any]) -> str | None:
        schedule = metadata.get("schedule_window")
        raw = metadata.get("publish_at")
        if schedule is not None:
            if not isinstance(schedule, dict):
                raise YouTubePublisherError("schedule_window must be an object")
            raw = raw or schedule.get("publish_at")
            if raw is None:
                raise YouTubePublisherError("schedule_window requires publish_at")
        if raw is None:
            return None
        scheduled = _parse_datetime(raw, "publish_at")
        if scheduled <= self.now().astimezone(timezone.utc):
            raise YouTubePublisherError("publish_at must be in the future")
        return scheduled.isoformat().replace("+00:00", "Z")

    def _resolve_metadata(
        self,
        requested: Path,
        source: dict[str, Any],
    ) -> tuple[Path, dict[str, Any], Path]:
        if isinstance(source.get("platforms"), dict):
            if source.get("live_publish_enabled") is not True:
                raise YouTubePublisherError("publisher plan does not explicitly enable live publishing")
            if source.get("approved_for_live_publish") is not True:
                raise YouTubePublisherError("publisher plan is not approved for live publishing")
            relative = source["platforms"].get("youtube_shorts")
            if not isinstance(relative, str) or not relative:
                raise YouTubePublisherError("publisher plan has no youtube_shorts metadata")
            metadata_file = (requested.parent / relative).resolve()
            job_root = requested.parent.parent.resolve()
            if not is_within(metadata_file, job_root):
                raise YouTubePublisherError("YouTube metadata path escapes its job directory")
            return metadata_file, self._read_json(metadata_file, "YouTube metadata"), job_root
        job_root = requested.parent.parent.parent.resolve()
        if not is_within(requested, job_root):
            raise YouTubePublisherError("YouTube metadata path escapes its job directory")
        return requested, source, job_root

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise YouTubePublisherError(f"{label} is missing")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise YouTubePublisherError(f"{label} must contain valid JSON") from exc
        if not isinstance(value, dict):
            raise YouTubePublisherError(f"{label} must contain a JSON object")
        return value


class YouTubePublishReceiptStore:
    def __init__(self, output_root: str | Path = "output"):
        self.root = Path(output_root).expanduser().resolve() / "autopilot" / "batches"

    def path_for(self, attempt: PublishAttempt) -> Path:
        if Path(attempt.batch_id).name != attempt.batch_id or not attempt.batch_id.startswith("ap_"):
            raise YouTubePublisherError("invalid autopilot batch id")
        if Path(attempt.publish_attempt_id).name != attempt.publish_attempt_id:
            raise YouTubePublisherError("invalid publish attempt id")
        path = self.root / attempt.batch_id / "publisher_receipts" / "youtube_shorts" / f"{attempt.publish_attempt_id}.json"
        if not is_within(path, self.root):
            raise YouTubePublisherError("publish receipt path escapes output root")
        return path

    def write(self, attempt: PublishAttempt, receipt: dict[str, Any]) -> Path:
        path = self.path_for(attempt)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".youtube-publish.", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(receipt, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path


class YouTubePublisherAdapter:
    platform = "youtube_shorts"

    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        credentials: YouTubeCredentials | None = None,
        credential_loader: Callable[[], YouTubeCredentials] = YouTubeCredentials.from_env,
        policy: YouTubeLivePolicy | None = None,
        policy_loader: Callable[[], YouTubeLivePolicy] = YouTubeLivePolicy.from_env,
        transport: YouTubeUploadTransport | None = None,
        now: Callable[[], datetime] = _utc_now,
    ):
        self._credentials = credentials
        self._credential_loader = credential_loader
        self._policy = policy
        self._policy_loader = policy_loader
        self.transport = transport or GoogleApiYouTubeUploadTransport()
        self.now = now
        self.payload_builder = YouTubeUploadPayloadBuilder(now=now)
        self.receipts = YouTubePublishReceiptStore(output_root)
        self.last_receipt_path: Path | None = None
        self._runtime_emergency_stop = False

    def preflight(self, *, config: AutopilotConfig) -> dict[str, Any]:
        self._runtime_emergency_stop = config.emergency_stop
        return self._preflight(mode=config.mode, emergency_stop=config.emergency_stop)

    def publish(self, *, attempt: PublishAttempt, package: dict[str, str]) -> PublishAttempt:
        if attempt.platform != self.platform:
            raise YouTubePublisherError("YouTube adapter received a non-YouTube attempt")
        if package.get("metadata_path") != attempt.metadata_path:
            raise YouTubePublisherError("publisher package does not match attempt")

        preflight = self._preflight(mode=attempt.mode, emergency_stop=self._runtime_emergency_stop)
        if preflight["ready"] is not True:
            blocked = replace(
                attempt,
                adapter="youtube_official",
                status="blocked",
                blocked_reason=str(preflight["reason"]),
                finished_at=self.now().isoformat(),
            )
            self._write_receipt(blocked, preflight=preflight, classification="blocked_live_publish", api_call_attempted=False)
            return blocked

        try:
            payload = self.payload_builder.build(attempt.metadata_path, expected_job_id=attempt.job_id)
        except YouTubePublisherError as exc:
            blocked = replace(
                attempt,
                adapter="youtube_official",
                status="blocked",
                blocked_reason=str(exc),
                finished_at=self.now().isoformat(),
            )
            self._write_receipt(blocked, preflight=preflight, classification="blocked_live_publish", api_call_attempted=False)
            return blocked

        credentials = self._get_credentials()
        try:
            response = self.transport.upload(access_token=credentials.access_token, payload=payload)
            video_id = response.get("id") if isinstance(response, dict) else None
            if not isinstance(video_id, str) or not video_id.strip():
                raise YouTubePublisherError("YouTube upload response is missing a video id")
        except Exception as exc:
            details = str(exc).replace(credentials.access_token, "[REDACTED]")
            failed = replace(
                attempt,
                adapter="youtube_official",
                status="failed",
                blocked_reason=f"YouTube upload failed: {type(exc).__name__}: {details[:240]}",
                finished_at=self.now().isoformat(),
            )
            self._write_receipt(
                failed,
                preflight=preflight,
                payload=payload,
                classification="failed_live_publish",
                api_call_attempted=True,
            )
            return failed

        published = replace(
            attempt,
            adapter="youtube_official",
            status="published",
            external_post_id=video_id,
            external_url=f"https://www.youtube.com/watch?v={video_id}",
            blocked_reason=None,
            finished_at=self.now().isoformat(),
        )
        self._write_receipt(
            published,
            preflight=preflight,
            payload=payload,
            classification="successful_live_publish_adapter_path",
            api_call_attempted=True,
        )
        return published

    def _preflight(self, *, mode: str, emergency_stop: bool) -> dict[str, Any]:
        if mode != "full_autopilot":
            return {
                "ready": False,
                "reason": "YouTube credentials are not read outside full_autopilot mode",
                "adapter": "youtube_official",
                "credentials_checked": False,
                "live_publishing_enabled": False,
                "checks": [{"name": "full_autopilot_mode", "passed": False}],
            }
        credentials = self._get_credentials()
        policy = self._get_policy()
        emergency_stop = emergency_stop or policy.emergency_stop
        checks = [
            {"name": "full_autopilot_mode", "passed": True},
            {"name": "emergency_stop_clear", "passed": not emergency_stop},
            {"name": "live_publishing_enabled", "passed": policy.live_publishing_enabled},
            {"name": "youtube_publishing_enabled", "passed": policy.youtube_publishing_enabled},
            {"name": "youtube_upload_quota_available", "passed": policy.quota_remaining >= 1},
            {"name": "youtube_policy_acknowledged", "passed": policy.policy_acknowledged},
            {"name": "youtube_credential_preflight_ready", "passed": policy.credential_preflight_ready},
            *credentials.checks(self.now().astimezone(timezone.utc)),
        ]
        failed = [check["name"] for check in checks if check["passed"] is not True]
        return {
            "ready": not failed,
            "reason": "YouTube live preflight passed" if not failed else f"YouTube live preflight blocked: {', '.join(failed)}",
            "adapter": "youtube_official",
            "credentials_checked": True,
            "credentials_present": bool(credentials.access_token),
            "quota_remaining_before_attempt": policy.quota_remaining,
            "live_publishing_enabled": policy.live_publishing_enabled and policy.youtube_publishing_enabled,
            "checks": checks,
        }

    def _get_credentials(self) -> YouTubeCredentials:
        if self._credentials is None:
            self._credentials = self._credential_loader()
        return self._credentials

    def _get_policy(self) -> YouTubeLivePolicy:
        if self._policy is None:
            self._policy = self._policy_loader()
        return self._policy

    def _write_receipt(
        self,
        result: PublishAttempt,
        *,
        preflight: dict[str, Any],
        classification: str,
        api_call_attempted: bool,
        payload: YouTubeUploadPayload | None = None,
    ) -> None:
        receipt = {
            "receipt_version": RECEIPT_VERSION,
            "classification": classification,
            "attempt": result.to_dict(),
            "preflight": preflight,
            "payload": payload.to_dict() if payload else None,
            "transport": self.transport.name,
            "api_call_attempted": api_call_attempted,
            "credentials_recorded": False,
            "oauth_required": True,
            "quota_check_required": True,
            "platform_policy_check_required": True,
            "created_at": self.now().isoformat(),
        }
        self.last_receipt_path = self.receipts.write(result, receipt)
