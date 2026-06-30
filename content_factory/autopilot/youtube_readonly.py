from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .youtube_credentials import DEFAULT_RECEIPT, GoogleYouTubeOAuthBackend
from .youtube_publisher import (
    YOUTUBE_ANALYTICS_READONLY_SCOPE,
    YouTubeCredentials,
)


EXPECTED_CHANNEL_ID = "UCIzMYpBt3WdSXZBrvoE7eCg"
EXPECTED_CHANNEL_TITLE = "Ghost Town Test"
URL_PATTERN = re.compile(r"https?://\S+", re.I)
SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|authorization|bearer|auth[_ -]?code)"
    r"\s*[:=]\s*[^\s,;]+"
)


class YouTubeReadOnlyError(ValueError):
    pass


class MissingAnalyticsScopeError(YouTubeReadOnlyError):
    pass


@dataclass(frozen=True)
class YouTubeReadOnlyAccess:
    channel_id: str
    channel_title: str
    credentials: YouTubeCredentials
    preflight_receipt: str


def redact_error(exc: BaseException, secrets: Sequence[str] = ()) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = URL_PATTERN.sub("[REDACTED_URL]", text)
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:500]


def read_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise YouTubeReadOnlyError(f"{label} is missing")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise YouTubeReadOnlyError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise YouTubeReadOnlyError(f"{label} must contain a JSON object")
    return value


def atomic_new_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".youtube-readonly.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_default_credentials(token_path: Path) -> YouTubeCredentials:
    state = GoogleYouTubeOAuthBackend().inspect_token(token_path=token_path)
    access_token = str(getattr(state.credentials, "token", "") or "")
    return YouTubeCredentials(access_token=access_token, scopes=state.scopes, expires_at=state.expires_at)


def authorize_readonly(
    *,
    preflight_receipt: str | Path = DEFAULT_RECEIPT,
    expected_channel_id: str,
    require_analytics_scope: bool,
    credential_loader: Callable[[Path], YouTubeCredentials] = load_default_credentials,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> YouTubeReadOnlyAccess:
    preflight_path = Path(preflight_receipt).expanduser().resolve()
    receipt = read_object(preflight_path, "YouTube credential preflight receipt")
    channel = receipt.get("channel")
    token = receipt.get("token")
    safety = receipt.get("safety")
    if not isinstance(channel, dict) or not isinstance(token, dict) or not isinstance(safety, dict):
        raise YouTubeReadOnlyError("YouTube credential preflight receipt is incomplete")
    if receipt.get("status") != "passed":
        raise YouTubeReadOnlyError("YouTube credential preflight status is not passed")
    if channel.get("status") != "verified":
        raise YouTubeReadOnlyError("YouTube channel identity preflight did not pass")
    if token.get("youtube_readonly_scope") is not True:
        raise YouTubeReadOnlyError("YouTube readonly scope is missing")
    if any(safety.get(name) is not False for name in ("upload_attempted", "videos_insert_called", "secrets_recorded")):
        raise YouTubeReadOnlyError("YouTube credential preflight safety evidence is invalid")
    channel_id = channel.get("id")
    channel_title = channel.get("title")
    if (
        expected_channel_id != EXPECTED_CHANNEL_ID
        or channel_id != EXPECTED_CHANNEL_ID
        or channel_title != EXPECTED_CHANNEL_TITLE
    ):
        raise YouTubeReadOnlyError("authenticated or expected channel does not match Ghost Town Test")
    if require_analytics_scope and token.get("youtube_analytics_readonly_scope") is not True:
        raise MissingAnalyticsScopeError(
            "YouTube analytics scope is missing; re-bootstrap with --include-analytics-scope and rerun preflight"
        )
    paths = receipt.get("paths")
    token_value = paths.get("token") if isinstance(paths, dict) else None
    if not isinstance(token_value, str) or not token_value.strip():
        raise YouTubeReadOnlyError("preflight receipt does not reference the authorized-user token")
    credentials = credential_loader(Path(token_value).expanduser().resolve())
    failed = [check["name"] for check in credentials.checks(now().astimezone(timezone.utc)) if check["passed"] is not True]
    if failed:
        raise YouTubeReadOnlyError("runtime YouTube credentials failed: " + ", ".join(failed))
    if require_analytics_scope and YOUTUBE_ANALYTICS_READONLY_SCOPE not in credentials.scopes:
        raise MissingAnalyticsScopeError(
            "runtime token lacks YouTube analytics scope; re-bootstrap with --include-analytics-scope"
        )
    return YouTubeReadOnlyAccess(
        channel_id=str(channel_id),
        channel_title=str(channel_title),
        credentials=credentials,
        preflight_receipt=str(preflight_path),
    )
