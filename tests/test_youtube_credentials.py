from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from content_factory.autopilot.autopilot_config import AutopilotConfig
from content_factory.autopilot.youtube_credentials import (
    TokenInspection,
    YouTubeCredentialManager,
    main,
)
from content_factory.autopilot.youtube_publisher import (
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_REQUIRED_SCOPES,
    YOUTUBE_UPLOAD_SCOPE,
    YouTubeLivePolicy,
    YouTubePublisherAdapter,
)


NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


class FakeBackend:
    name = "fake_google_oauth"

    def __init__(self) -> None:
        self.bootstrap_calls = 0
        self.inspect_calls = 0
        self.channel_calls = 0

    @staticmethod
    def dependency_status():
        return {
            "google-api-python-client": True,
            "google-auth": True,
            "google-auth-oauthlib": True,
            "google-auth-httplib2": True,
        }

    def bootstrap(self, *, client_secret_path, token_path, open_browser):
        self.bootstrap_calls += 1
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(
            json.dumps({"token": "secret-token", "scopes": list(YOUTUBE_REQUIRED_SCOPES)}),
            encoding="utf-8",
        )
        return self._state()

    def inspect_token(self, *, token_path):
        self.inspect_calls += 1
        return self._state()

    def channel_identity(self, *, credentials):
        self.channel_calls += 1
        return {"id": "UC-local-test", "title": "Local Test Channel"}

    @staticmethod
    def _state():
        return TokenInspection(
            credentials=object(),
            valid=True,
            refreshable=True,
            refreshed=False,
            scopes=YOUTUBE_REQUIRED_SCOPES,
            expires_at="2026-06-30T12:00:00+00:00",
        )


class InvalidRefreshableBackend(FakeBackend):
    def inspect_token(self, *, token_path):
        self.inspect_calls += 1
        return TokenInspection(
            credentials=object(),
            valid=False,
            refreshable=True,
            refreshed=False,
            scopes=YOUTUBE_REQUIRED_SCOPES,
            expires_at=None,
        )


class MissingScopeBackend(FakeBackend):
    def inspect_token(self, *, token_path):
        self.inspect_calls += 1
        return TokenInspection(
            credentials=object(),
            valid=True,
            refreshable=True,
            refreshed=False,
            scopes=(),
            expires_at="2026-06-30T12:00:00+00:00",
        )


class UploadOnlyBackend(FakeBackend):
    def inspect_token(self, *, token_path):
        self.inspect_calls += 1
        return TokenInspection(
            credentials=object(),
            valid=True,
            refreshable=True,
            refreshed=False,
            scopes=(YOUTUBE_UPLOAD_SCOPE,),
            expires_at="2026-06-30T12:00:00+00:00",
        )


class ChannelHttpErrorBackend(FakeBackend):
    def channel_identity(self, *, credentials):
        self.channel_calls += 1
        error_type = type("HttpError", (Exception,), {})
        error = error_type("secret-token must never enter the receipt")
        error.resp = SimpleNamespace(status=403)
        error.content = json.dumps({
            "error": {
                "errors": [{"reason": "insufficientPermissions"}],
                "message": "secret-token client-secret auth-code",
            }
        }).encode("utf-8")
        raise error


def _installed_client() -> dict:
    return {
        "installed": {
            "client_id": "local-client.apps.googleusercontent.com",
            "client_secret": "local-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _manager(tmp_path: Path, backend: FakeBackend | None = None) -> YouTubeCredentialManager:
    return YouTubeCredentialManager(
        repo_root=Path(__file__).resolve().parents[1],
        client_secret_path=tmp_path / "client_secret.json",
        token_path=tmp_path / "token.json",
        receipt_path=tmp_path / "receipt.json",
        backend=backend or FakeBackend(),
        now=lambda: NOW,
    )


def test_dry_run_never_reads_youtube_credential_files(tmp_path, monkeypatch):
    token = tmp_path / "must-not-be-read.json"
    token.write_text("not json", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_TOKEN_FILE", str(token))
    original = Path.read_text
    reads = 0

    def guarded_read(path, *args, **kwargs):
        nonlocal reads
        if path.resolve() == token.resolve():
            reads += 1
            raise AssertionError("dry_run read the YouTube token file")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    adapter = YouTubePublisherAdapter(output_root=tmp_path)
    result = adapter.preflight(config=AutopilotConfig(mode="dry_run"))
    assert result["ready"] is False
    assert result["credentials_checked"] is False
    assert reads == 0


def test_missing_client_secret_fails_safely_and_writes_receipt(tmp_path):
    manager = _manager(tmp_path)
    result = manager.preflight()
    assert result["status"] == "blocked"
    assert any(row["name"] == "client_secret_exists" and row["passed"] is False for row in result["checks"])
    assert Path(result["receipt_path"]).is_file()
    assert result["safety"]["upload_attempted"] is False


def test_missing_token_fails_safely(tmp_path):
    manager = _manager(tmp_path)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    result = manager.preflight()
    assert result["status"] == "blocked"
    assert any(row["name"] == "token_exists" and row["passed"] is False for row in result["checks"])
    assert manager.backend.inspect_calls == 0


def test_default_token_and_client_paths_are_git_ignored():
    repo = Path(__file__).resolve().parents[1]
    manager = YouTubeCredentialManager(repo_root=repo)
    paths = manager.paths()
    assert paths["client_secret_git_ignored"] is True
    assert paths["token_git_ignored"] is True
    assert paths["client_secret_path"].endswith(".local\\youtube\\client_secret.json") or paths["client_secret_path"].endswith(".local/youtube/client_secret.json")
    assert paths["token_path"].endswith(".local\\youtube\\token.json") or paths["token_path"].endswith(".local/youtube/token.json")


def test_local_environment_secret_files_are_git_ignored():
    repo = Path(__file__).resolve().parents[1]
    manager = YouTubeCredentialManager(repo_root=repo)
    assert manager._git_ignored(repo / ".env") is True
    assert manager._git_ignored(repo / ".env.local") is True


def test_service_account_client_config_is_refused(tmp_path):
    manager = _manager(tmp_path)
    manager.client_secret_path.write_text(json.dumps({
        "type": "service_account",
        "client_email": "not-allowed@example.test",
        "private_key": "never-real",
    }), encoding="utf-8")
    manager.token_path.write_text("{}", encoding="utf-8")
    result = manager.preflight()
    assert result["status"] == "blocked"
    installed = next(row for row in result["checks"] if row["name"] == "installed_app_client")
    assert installed["passed"] is False
    assert "service account" in installed["detail"]
    assert result["safety"]["service_accounts_allowed"] is False


def test_preflight_receipt_is_durable_redacted_and_records_channel(tmp_path):
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text(json.dumps({"token": "secret-token"}), encoding="utf-8")
    result = manager.preflight(confirm_quota_ready=True, confirm_policy_ready=True)
    assert result["status"] == "passed"
    assert result["channel"] == {
        "status": "verified",
        "id": "UC-local-test",
        "title": "Local Test Channel",
    }
    assert result["readiness"]["ready_for_future_supervised_upload"] is True
    assert result["readiness"]["full_autopilot_enabled"] is False
    assert result["readiness"]["supervised_autopilot_enabled"] is False
    assert backend.channel_calls == 1
    checks = {row["name"]: row["passed"] for row in result["checks"]}
    assert checks["youtube_upload_scope"] is True
    assert checks["youtube_readonly_scope"] is True
    persisted = Path(result["receipt_path"]).read_text(encoding="utf-8")
    assert "secret-token" not in persisted
    assert "local-secret" not in persisted
    assert json.loads(persisted)["safety"]["videos_insert_called"] is False


def test_preflight_without_quota_and_policy_confirmation_keeps_gate_closed(tmp_path):
    manager = _manager(tmp_path)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text("{}", encoding="utf-8")
    result = manager.preflight()
    assert result["status"] == "passed"
    assert result["readiness"]["quota_console_confirmation"] is False
    assert result["readiness"]["policy_approval_confirmation"] is False
    assert result["readiness"]["ready_for_future_supervised_upload"] is False


def test_refreshable_but_invalid_token_still_blocks_channel_and_readiness(tmp_path):
    backend = InvalidRefreshableBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text("{}", encoding="utf-8")
    result = manager.preflight(confirm_quota_ready=True, confirm_policy_ready=True)
    assert result["status"] == "blocked"
    assert result["channel"]["status"] == "not_checked"
    assert result["readiness"]["ready_for_future_supervised_upload"] is False
    assert backend.channel_calls == 0


def test_missing_upload_scope_blocks_before_channel_lookup(tmp_path):
    backend = MissingScopeBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text("{}", encoding="utf-8")
    result = manager.preflight(confirm_quota_ready=True, confirm_policy_ready=True)
    scope = next(row for row in result["checks"] if row["name"] == "youtube_upload_scope")
    assert scope["passed"] is False
    assert result["status"] == "blocked"
    assert backend.channel_calls == 0


def test_upload_only_token_fails_readonly_scope_gate_without_channel_lookup(tmp_path):
    backend = UploadOnlyBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text("{}", encoding="utf-8")
    result = manager.preflight(confirm_quota_ready=True, confirm_policy_ready=True)
    checks = {row["name"]: row for row in result["checks"]}
    assert checks["youtube_upload_scope"]["passed"] is True
    assert checks["youtube_readonly_scope"]["passed"] is False
    assert checks["channel_identity"]["passed"] is False
    assert "upload and readonly scopes" in checks["channel_identity"]["detail"]
    assert result["status"] == "blocked"
    assert backend.channel_calls == 0


def test_channel_http_error_receipt_keeps_only_safe_status_and_reason(tmp_path):
    backend = ChannelHttpErrorBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    manager.token_path.write_text(json.dumps({"token": "secret-token"}), encoding="utf-8")
    result = manager.preflight()
    channel_check = next(row for row in result["checks"] if row["name"] == "channel_identity")
    assert channel_check["detail"] == "HttpError: status=403 reason=insufficientPermissions"
    persisted = Path(result["receipt_path"]).read_text(encoding="utf-8")
    assert "secret-token" not in persisted
    assert "client-secret" not in persisted
    assert "auth-code" not in persisted


def test_bootstrap_uses_installed_app_backend_and_required_scopes(tmp_path):
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    manager.client_secret_path.write_text(json.dumps(_installed_client()), encoding="utf-8")
    result = manager.bootstrap(open_browser=True)
    assert backend.bootstrap_calls == 1
    assert result["status"] == "token_saved"
    assert result["scopes"] == [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]
    assert result["upload_attempted"] is False


def test_environment_live_policy_requires_passed_confirmed_preflight_receipt(tmp_path, monkeypatch):
    receipt = tmp_path / "preflight.json"
    monkeypatch.setenv("YOUTUBE_PREFLIGHT_RECEIPT", str(receipt))
    assert YouTubeLivePolicy.from_env().credential_preflight_ready is False
    receipt.write_text(json.dumps({
        "status": "passed",
        "channel": {"status": "verified", "id": "UC-test", "title": "Test"},
        "token": {"youtube_upload_scope": True, "youtube_readonly_scope": False},
        "readiness": {"ready_for_future_supervised_upload": True},
    }), encoding="utf-8")
    assert YouTubeLivePolicy.from_env().credential_preflight_ready is False
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["token"]["youtube_readonly_scope"] = True
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert YouTubeLivePolicy.from_env().credential_preflight_ready is True


def test_cli_missing_client_secret_returns_failure_and_receipt(tmp_path, capsys):
    receipt = tmp_path / "cli-receipt.json"
    exit_code = main([
        "preflight",
        "--client-secret", str(tmp_path / "missing.json"),
        "--token", str(tmp_path / "missing-token.json"),
        "--receipt", str(receipt),
    ])
    assert exit_code == 1
    assert receipt.is_file()
    assert "Preflight receipt:" in capsys.readouterr().out
