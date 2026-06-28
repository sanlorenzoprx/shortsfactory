from __future__ import annotations

from pathlib import Path

from content_factory.launcher import health_check
from content_factory.launcher.health_check import run_health_check
from content_factory.launcher.paths import CLI_FILES, LauncherPaths


def test_health_check_runs_locally_and_reports_cli_files():
    report = run_health_check(LauncherPaths.default())
    checks = {item["name"]: item for item in report["checks"]}
    assert report["status"] in {"pass", "warn"}
    assert report["live_publishing_enabled"] is False
    for name in CLI_FILES:
        assert checks[f"cli_file:{name}"]["status"] == "pass"
    assert checks["templates"]["status"] == "pass"
    assert checks["demo_dataset_git"]["status"] == "pass"


def test_health_check_reports_missing_ffmpeg_as_warning(monkeypatch):
    original = health_check.shutil.which
    monkeypatch.setattr(
        health_check.shutil,
        "which",
        lambda name: None if name == "ffmpeg" else original(name),
    )
    report = run_health_check(LauncherPaths.default())
    ffmpeg = next(item for item in report["checks"] if item["name"] == "ffmpeg")
    assert ffmpeg["status"] == "warn"
    assert report["status"] == "warn"


def test_health_check_warns_for_missing_optional_import(monkeypatch):
    original = health_check.importlib.util.find_spec
    monkeypatch.setattr(
        health_check.importlib.util,
        "find_spec",
        lambda name: None if name == "dotenv" else original(name),
    )
    report = run_health_check(LauncherPaths.default())
    missing = next(item for item in report["checks"] if item["name"] == "python_import:dotenv")
    assert missing["status"] == "warn"
    assert report["status"] == "warn"
