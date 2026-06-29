from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from content_factory.mission_control.job_index import is_within

from .youtube_publisher import (
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_REQUIRED_SCOPES,
    YOUTUBE_UPLOAD_SCOPE,
)


PREFLIGHT_VERSION = "phase5b.1.youtube-credentials.v1"
DEFAULT_CLIENT_SECRET = Path(".local/youtube/client_secret.json")
DEFAULT_TOKEN = Path(".local/youtube/token.json")
DEFAULT_RECEIPT = Path("output/youtube/credential_preflight/YOUTUBE_CREDENTIAL_PREFLIGHT.json")


class YouTubeCredentialError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".youtube-credentials.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


@dataclass(frozen=True)
class TokenInspection:
    credentials: Any = field(repr=False, compare=False)
    valid: bool
    refreshable: bool
    refreshed: bool
    scopes: tuple[str, ...]
    expires_at: str | None


class YouTubeOAuthBackend(Protocol):
    name: str

    def dependency_status(self) -> dict[str, bool]: ...

    def bootstrap(
        self,
        *,
        client_secret_path: Path,
        token_path: Path,
        open_browser: bool,
    ) -> TokenInspection: ...

    def inspect_token(self, *, token_path: Path) -> TokenInspection: ...

    def channel_identity(self, *, credentials: Any) -> dict[str, str]: ...


class GoogleYouTubeOAuthBackend:
    name = "google_installed_app_oauth"

    @staticmethod
    def dependency_status() -> dict[str, bool]:
        modules = {
            "google-api-python-client": "googleapiclient.discovery",
            "google-auth": "google.oauth2.credentials",
            "google-auth-oauthlib": "google_auth_oauthlib.flow",
            "google-auth-httplib2": "google_auth_httplib2",
        }
        status: dict[str, bool] = {}
        for package, module in modules.items():
            try:
                available = importlib.util.find_spec(module) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                status[package] = False
            else:
                status[package] = available
        return status

    def bootstrap(
        self,
        *,
        client_secret_path: Path,
        token_path: Path,
        open_browser: bool,
    ) -> TokenInspection:
        self._require_dependencies()
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            scopes=list(YOUTUBE_REQUIRED_SCOPES),
        )
        credentials = flow.run_local_server(
            port=0,
            open_browser=open_browser,
            access_type="offline",
            prompt="consent",
            authorization_prompt_message=(
                "Open this URL to authorize YouTube upload and channel identity access:\n{url}"
            ),
            success_message="YouTube credential bootstrap complete. You may close this browser window.",
        )
        self._write_credentials(token_path, credentials)
        return self._state(credentials, refreshed=False)

    def inspect_token(self, *, token_path: Path) -> TokenInspection:
        self._require_dependencies()
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials.from_authorized_user_file(str(token_path))
        refreshed = False
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._write_credentials(token_path, credentials)
            refreshed = True
        return self._state(credentials, refreshed=refreshed)

    def channel_identity(self, *, credentials: Any) -> dict[str, str]:
        self._require_dependencies()
        from googleapiclient.discovery import build

        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        try:
            response = service.channels().list(part="id,snippet", mine=True).execute()
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
        items = response.get("items", []) if isinstance(response, dict) else []
        if not items or not isinstance(items[0], dict):
            raise YouTubeCredentialError("authenticated Google account has no YouTube channel")
        channel = items[0]
        snippet = channel.get("snippet", {}) if isinstance(channel.get("snippet"), dict) else {}
        channel_id = channel.get("id")
        title = snippet.get("title")
        if not isinstance(channel_id, str) or not channel_id.strip():
            raise YouTubeCredentialError("authenticated YouTube channel id is missing")
        if not isinstance(title, str) or not title.strip():
            raise YouTubeCredentialError("authenticated YouTube channel title is missing")
        return {"id": channel_id.strip(), "title": title.strip()}

    def _require_dependencies(self) -> None:
        missing = [name for name, installed in self.dependency_status().items() if not installed]
        if missing:
            raise YouTubeCredentialError(
                "Missing optional YouTube dependencies: "
                + ", ".join(missing)
                + ". Run: python -m pip install -r requirements-youtube.txt"
            )

    @staticmethod
    def _write_credentials(path: Path, credentials: Any) -> None:
        try:
            value = json.loads(credentials.to_json())
        except (AttributeError, TypeError, json.JSONDecodeError) as exc:
            raise YouTubeCredentialError("Google returned an invalid authorized-user token") from exc
        _atomic_json(path, value)

    @staticmethod
    def _state(credentials: Any, *, refreshed: bool) -> TokenInspection:
        scopes = tuple(credentials.scopes or getattr(credentials, "granted_scopes", None) or ())
        expiry = credentials.expiry
        if isinstance(expiry, datetime):
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            expires_at = expiry.astimezone(timezone.utc).isoformat()
        else:
            expires_at = None
        return TokenInspection(
            credentials=credentials,
            valid=bool(credentials.valid),
            refreshable=bool(credentials.refresh_token),
            refreshed=refreshed,
            scopes=scopes,
            expires_at=expires_at,
        )


class YouTubeCredentialManager:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        client_secret_path: str | Path = DEFAULT_CLIENT_SECRET,
        token_path: str | Path = DEFAULT_TOKEN,
        receipt_path: str | Path = DEFAULT_RECEIPT,
        backend: YouTubeOAuthBackend | None = None,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.client_secret_path = self._resolve(client_secret_path)
        self.token_path = self._resolve(token_path)
        self.receipt_path = self._resolve(receipt_path)
        self.backend = backend or GoogleYouTubeOAuthBackend()
        self.now = now

    def paths(self) -> dict[str, Any]:
        return {
            "client_secret_path": str(self.client_secret_path),
            "token_path": str(self.token_path),
            "receipt_path": str(self.receipt_path),
            "client_secret_git_ignored": self._git_ignored(self.client_secret_path),
            "token_git_ignored": self._git_ignored(self.token_path),
        }

    def bootstrap(self, *, open_browser: bool = True) -> dict[str, Any]:
        self._validate_secret_path_safety()
        self._validate_installed_client_file()
        state = self.backend.bootstrap(
            client_secret_path=self.client_secret_path,
            token_path=self.token_path,
            open_browser=open_browser,
        )
        if not self.token_path.is_file():
            raise YouTubeCredentialError("OAuth flow completed without writing the local token file")
        missing_scopes = [scope for scope in YOUTUBE_REQUIRED_SCOPES if scope not in state.scopes]
        if missing_scopes:
            raise YouTubeCredentialError(
                "OAuth flow did not grant required YouTube scopes: " + ", ".join(missing_scopes)
            )
        return {
            "status": "token_saved",
            "token_path": str(self.token_path),
            "scopes": list(YOUTUBE_REQUIRED_SCOPES),
            "valid": state.valid,
            "refreshable": state.refreshable,
            "secrets_printed": False,
            "upload_attempted": False,
        }

    def preflight(
        self,
        *,
        confirm_quota_ready: bool = False,
        confirm_policy_ready: bool = False,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        token_summary: dict[str, Any] = {
            "valid": False,
            "refreshable": False,
            "refreshed": False,
            "youtube_upload_scope": False,
            "youtube_readonly_scope": False,
            "expires_at": None,
        }
        channel: dict[str, Any] = {"status": "not_checked", "id": None, "title": None}
        dependencies = self.backend.dependency_status()

        def add(name: str, passed: bool, detail: str) -> None:
            checks.append({"name": name, "passed": passed, "detail": detail})

        add("optional_dependencies", all(dependencies.values()), self._dependency_detail(dependencies))
        add("client_secret_exists", self.client_secret_path.is_file(), "installed-app client JSON is local")
        add("client_secret_git_ignored", self._git_ignored(self.client_secret_path), "client secret path must be ignored")
        add("token_exists", self.token_path.is_file(), "authorized-user token JSON is local")
        add("token_git_ignored", self._git_ignored(self.token_path), "token path must be ignored")

        client_valid = False
        if self.client_secret_path.is_file():
            try:
                self._validate_installed_client_file()
            except YouTubeCredentialError as exc:
                add("installed_app_client", False, str(exc))
            else:
                client_valid = True
                add("installed_app_client", True, "installed OAuth client configuration")

        state: TokenInspection | None = None
        prerequisites = all(dependencies.values()) and client_valid and self.token_path.is_file()
        if prerequisites:
            try:
                self._reject_service_account_file(self.token_path, "token")
                state = self.backend.inspect_token(token_path=self.token_path)
            except Exception as exc:
                add("authorized_user_token", False, self._safe_error(exc))
            else:
                add("authorized_user_token", True, "authorized-user OAuth token loaded")
                token_summary = {
                    "valid": state.valid,
                    "refreshable": state.refreshable,
                    "refreshed": state.refreshed,
                    "youtube_upload_scope": YOUTUBE_UPLOAD_SCOPE in state.scopes,
                    "youtube_readonly_scope": YOUTUBE_READONLY_SCOPE in state.scopes,
                    "expires_at": state.expires_at,
                }
                add(
                    "token_valid_or_refreshable",
                    state.valid or state.refreshable,
                    "token is valid or has a refresh token",
                )
                add(
                    "youtube_upload_scope",
                    YOUTUBE_UPLOAD_SCOPE in state.scopes,
                    "least-privilege YouTube upload scope is granted",
                )
                add(
                    "youtube_readonly_scope",
                    YOUTUBE_READONLY_SCOPE in state.scopes,
                    "YouTube readonly scope is granted for channel identity preflight",
                )
                has_required_scopes = all(scope in state.scopes for scope in YOUTUBE_REQUIRED_SCOPES)
                if state.valid and has_required_scopes:
                    try:
                        identity = self.backend.channel_identity(credentials=state.credentials)
                    except Exception as exc:
                        channel = {"status": "unavailable", "id": None, "title": None, "detail": self._safe_error(exc)}
                        add("channel_identity", False, channel["detail"])
                    else:
                        channel = {"status": "verified", "id": identity["id"], "title": identity["title"]}
                        add("channel_identity", True, "authenticated channel identity verified")
                else:
                    add(
                        "channel_identity",
                        False,
                        "token must be valid with YouTube upload and readonly scopes before channel lookup",
                    )

        credential_checks = {
            "optional_dependencies",
            "client_secret_exists",
            "client_secret_git_ignored",
            "token_exists",
            "token_git_ignored",
            "installed_app_client",
            "authorized_user_token",
            "token_valid_or_refreshable",
            "youtube_upload_scope",
            "youtube_readonly_scope",
            "channel_identity",
        }
        relevant = [check for check in checks if check["name"] in credential_checks]
        credential_preflight_passed = bool(relevant) and all(check["passed"] for check in relevant)
        ready = credential_preflight_passed and confirm_quota_ready and confirm_policy_ready
        receipt = {
            "receipt_version": PREFLIGHT_VERSION,
            "status": "passed" if credential_preflight_passed else "blocked",
            "created_at": self.now().astimezone(timezone.utc).isoformat(),
            "paths": {
                "client_secret": str(self.client_secret_path),
                "token": str(self.token_path),
            },
            "dependencies": dependencies,
            "checks": checks,
            "token": token_summary,
            "channel": channel,
            "readiness": {
                "quota_console_confirmation": confirm_quota_ready,
                "policy_approval_confirmation": confirm_policy_ready,
                "ready_for_future_supervised_upload": ready,
                "full_autopilot_enabled": False,
                "supervised_autopilot_enabled": False,
                "quota_note": "Confirm current upload quota in Google Cloud Console before a future upload.",
                "policy_note": "Google OAuth/app verification and YouTube API policy review may be required for production use.",
            },
            "safety": {
                "upload_attempted": False,
                "videos_insert_called": False,
                "live_publishing_enabled": False,
                "service_accounts_allowed": False,
                "secrets_recorded": False,
            },
        }
        _atomic_json(self.receipt_path, receipt)
        receipt["receipt_path"] = str(self.receipt_path)
        return receipt

    def _validate_secret_path_safety(self) -> None:
        if self.client_secret_path == self.token_path:
            raise YouTubeCredentialError("client secret and token paths must be different")
        for path, label in (
            (self.client_secret_path, "client secret"),
            (self.token_path, "token"),
        ):
            if not self._git_ignored(path):
                raise YouTubeCredentialError(f"{label} path must be outside Git tracking or covered by .gitignore")

    def _validate_installed_client_file(self) -> None:
        if not self.client_secret_path.is_file():
            raise YouTubeCredentialError(f"client secret file is missing: {self.client_secret_path}")
        value = self._read_json(self.client_secret_path, "client secret")
        self._reject_service_account(value, "client secret")
        installed = value.get("installed")
        if not isinstance(installed, dict):
            if isinstance(value.get("web"), dict):
                raise YouTubeCredentialError("web OAuth client is not allowed; create a Desktop app client")
            raise YouTubeCredentialError("client secret must contain an installed-app OAuth configuration")
        required = ("client_id", "client_secret", "auth_uri", "token_uri", "redirect_uris")
        if any(installed.get(name) in (None, "", []) for name in required):
            raise YouTubeCredentialError("installed-app client secret is incomplete")

    def _reject_service_account_file(self, path: Path, label: str) -> None:
        self._reject_service_account(self._read_json(path, label), label)

    @staticmethod
    def _reject_service_account(value: dict[str, Any], label: str) -> None:
        if value.get("type") == "service_account" or "private_key" in value or "client_email" in value:
            raise YouTubeCredentialError(
                f"{label} uses a service account; YouTube uploads require installed-app user OAuth"
            )

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise YouTubeCredentialError(f"{label} must contain valid JSON") from exc
        if not isinstance(value, dict):
            raise YouTubeCredentialError(f"{label} must contain a JSON object")
        return value

    def _git_ignored(self, path: Path) -> bool:
        if not is_within(path, self.repo_root):
            return True
        try:
            result = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(path)],
                cwd=self.repo_root,
                shell=False,
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return (self.repo_root / path).resolve() if not path.is_absolute() else path.resolve()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if type(exc).__name__ == "HttpError":
            status = getattr(getattr(exc, "resp", None), "status", None)
            reason = None
            content = getattr(exc, "content", None)
            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8")
                except UnicodeError:
                    content = None
            if isinstance(content, str):
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    payload = {}
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                errors = error.get("errors", []) if isinstance(error, dict) else []
                if errors and isinstance(errors[0], dict) and isinstance(errors[0].get("reason"), str):
                    reason = errors[0]["reason"]
                elif isinstance(error.get("status"), str):
                    reason = error["status"]
            return f"HttpError: status={status if status is not None else 'unknown'} reason={reason or 'unknown'}"
        if isinstance(exc, YouTubeCredentialError):
            return f"{type(exc).__name__}: {' '.join(str(exc).split())[:240]}"
        return f"{type(exc).__name__}: credential or channel validation failed; no secret details were recorded"

    @staticmethod
    def _dependency_detail(status: dict[str, bool]) -> str:
        missing = [name for name, installed in status.items() if not installed]
        return "all optional YouTube dependencies are installed" if not missing else "missing: " + ", ".join(missing)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap and preflight local YouTube installed-app OAuth credentials without uploading."
    )
    parser.add_argument("--client-secret", default=os.getenv("YOUTUBE_CLIENT_SECRET_FILE", str(DEFAULT_CLIENT_SECRET)))
    parser.add_argument("--token", default=os.getenv("YOUTUBE_TOKEN_FILE", str(DEFAULT_TOKEN)))
    parser.add_argument("--receipt", default=os.getenv("YOUTUBE_PREFLIGHT_RECEIPT", str(DEFAULT_RECEIPT)))
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_path_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--client-secret", dest="client_secret", default=argparse.SUPPRESS)
        command.add_argument("--token", dest="token", default=argparse.SUPPRESS)
        command.add_argument("--receipt", dest="receipt", default=argparse.SUPPRESS)

    bootstrap = subparsers.add_parser("bootstrap", help="Run the local installed-app OAuth browser flow")
    add_path_options(bootstrap)
    bootstrap.add_argument("--no-browser", action="store_true", help="Print the authorization URL instead of opening it")
    preflight = subparsers.add_parser("preflight", help="Validate local credentials and read channel identity")
    add_path_options(preflight)
    preflight.add_argument("--confirm-quota-ready", action="store_true")
    preflight.add_argument("--confirm-policy-ready", action="store_true")
    paths = subparsers.add_parser("paths", help="Show local credential paths and Git-ignore status")
    add_path_options(paths)
    dependencies = subparsers.add_parser("dependencies", help="Show optional dependency availability")
    add_path_options(dependencies)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = YouTubeCredentialManager(
        client_secret_path=args.client_secret,
        token_path=args.token,
        receipt_path=args.receipt,
    )
    try:
        if args.command == "bootstrap":
            result = manager.bootstrap(open_browser=not args.no_browser)
        elif args.command == "preflight":
            result = manager.preflight(
                confirm_quota_ready=args.confirm_quota_ready,
                confirm_policy_ready=args.confirm_policy_ready,
            )
            channel = result["channel"]
            if channel["status"] == "verified":
                print(f"Authenticated channel: {channel['title']} ({channel['id']})")
            print(f"Preflight receipt: {result['receipt_path']}")
            print(f"Future supervised upload ready: {result['readiness']['ready_for_future_supervised_upload']}")
            if result["status"] != "passed":
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 1
            return 0
        elif args.command == "paths":
            result = manager.paths()
        else:
            result = manager.backend.dependency_status()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except YouTubeCredentialError as exc:
        print(f"YouTube credential setup refused: {exc}", file=sys.stderr)
        return 1
