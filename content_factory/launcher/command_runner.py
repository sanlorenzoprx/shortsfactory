from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import LauncherPaths


RunFunction = Callable[..., subprocess.CompletedProcess[Any]]


@dataclass(frozen=True)
class LauncherCommand:
    label: str
    args: tuple[str, ...]


def _python_script(paths: LauncherPaths, script: str, *args: object) -> tuple[str, ...]:
    return (sys.executable, str(paths.script(script).resolve()), *(str(value) for value in args))


def mission_control_command(paths: LauncherPaths) -> LauncherCommand:
    return LauncherCommand(
        "Start Mission Control",
        _python_script(
            paths,
            "mission_control.py",
            "--output-root",
            paths.output_root,
            "--export-root",
            paths.export_root,
            "--template-root",
            paths.template_root,
            "--host",
            "127.0.0.1",
        ),
    )


def generate_mock_command(paths: LauncherPaths) -> LauncherCommand:
    return LauncherCommand(
        "Generate new mock short",
        _python_script(paths, "orchestrator.py", "--batch", 1, "--locale", "en-US", "--mode", "mock", "--tts", "--music", "--output-dir", paths.output_root),
    )


def generate_api_command(paths: LauncherPaths) -> LauncherCommand:
    return LauncherCommand(
        "Generate new API short",
        _python_script(paths, "orchestrator.py", "--batch", 1, "--locale", "en-US", "--mode", "api", "--record-app", "--tts", "--music", "--output-dir", paths.output_root),
    )


def score_command(paths: LauncherPaths, job_id: str) -> LauncherCommand:
    return LauncherCommand(
        f"Score job {job_id}",
        _python_script(paths, "score_job.py", "--job-id", job_id, "--output-root", paths.output_root),
    )


def audit_command(paths: LauncherPaths) -> LauncherCommand:
    return LauncherCommand(
        "Run Phase 3 audit",
        _python_script(paths, "phase3_audit.py", "--output-root", paths.output_root, "--export-root", paths.export_root, "--demo-root", paths.demo_root, "--template-root", paths.template_root),
    )


class CommandRunner:
    def __init__(self, paths: LauncherPaths, run_function: RunFunction = subprocess.run):
        self.paths = paths
        self._run = run_function

    def run(self, command: LauncherCommand) -> int:
        print(f"\n{command.label}")
        try:
            completed = self._run(
                list(command.args),
                cwd=str(self.paths.repo_root),
                shell=False,
                check=False,
            )
        except KeyboardInterrupt:
            print("Command stopped by local user.")
            return 130
        except OSError as exc:
            print(f"Could not start command: {exc}")
            return 1
        code = int(completed.returncode)
        if code != 0:
            print(f"Command finished with exit code {code}.")
        return code


def help_command(paths: LauncherPaths, script: str) -> tuple[str, ...]:
    return _python_script(paths, script, "--help")
