from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from content_factory.launcher.command_runner import (
    CommandRunner,
    audit_command,
    generate_api_command,
    mission_control_command,
)
from content_factory.launcher.paths import LauncherPaths, latest_job_id


def test_command_runner_uses_list_args_and_handles_space_paths(tmp_path: Path):
    root = tmp_path / "Shorts Factory with spaces"
    root.mkdir()
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    paths = LauncherPaths(root)
    result = CommandRunner(paths, fake_run).run(mission_control_command(paths))

    assert result == 0
    args, kwargs = calls[0]
    assert isinstance(args, list)
    assert args[0] == sys.executable
    assert str(root.resolve() / "mission_control.py") in args
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(root.resolve())


def test_mission_control_and_audit_commands_are_local_and_complete(tmp_path: Path):
    paths = LauncherPaths(tmp_path / "repo with spaces")
    mission = list(mission_control_command(paths).args)
    audit = list(audit_command(paths).args)

    assert mission[0] == sys.executable
    assert mission[1].endswith("mission_control.py")
    assert mission[mission.index("--host") + 1] == "127.0.0.1"
    assert "0.0.0.0" not in mission
    assert audit[1].endswith("phase3_audit.py")
    assert audit[audit.index("--output-root") + 1] == str(paths.output_root)
    assert audit[audit.index("--export-root") + 1] == str(paths.export_root)
    assert audit[audit.index("--demo-root") + 1] == str(paths.demo_root)


def test_api_generation_command_preserves_existing_fallback_workflow(tmp_path: Path):
    args = list(generate_api_command(LauncherPaths(tmp_path)).args)
    assert args[args.index("--mode") + 1] == "api"
    assert "--record-app" in args
    assert "--tts" in args
    assert "--music" in args


def test_latest_job_finder_ignores_folders_without_receipts(tmp_path: Path):
    jobs = tmp_path / "output" / "jobs"
    invalid = jobs / "newer-but-invalid"
    older = jobs / "older-valid"
    newest = jobs / "newest-valid"
    for directory in (invalid, older, newest):
        directory.mkdir(parents=True)
    (invalid / "script.txt").write_text("no receipt", encoding="utf-8")
    older_receipt = older / "receipt.json"
    newest_receipt = newest / "receipt.json"
    older_receipt.write_text("{}", encoding="utf-8")
    newest_receipt.write_text("{}", encoding="utf-8")
    os.utime(older_receipt, (1, 1))
    os.utime(newest_receipt, (2, 2))

    assert latest_job_id(tmp_path / "output") == "newest-valid"
