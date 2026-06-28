from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_factory.templates import TemplateStore

from .command_runner import help_command
from .paths import CLI_FILES, LauncherPaths


REQUIRED_IMPORTS = ("PIL",)
OPTIONAL_IMPORTS = ("dotenv",)
HELP_SCRIPTS = (
    "mission_control.py",
    "score_job.py",
    "export_bundle.py",
    "revise_job.py",
    "upload_kit.py",
    "template_editor.py",
    "phase3_audit.py",
)


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def run_health_check(paths: LauncherPaths | None = None) -> dict[str, Any]:
    paths = paths or LauncherPaths.default()
    checks: list[dict[str, str]] = []
    version = sys.version_info
    checks.append(_check("python", "pass" if version >= (3, 10) else "fail", f"Python {version.major}.{version.minor}.{version.micro}"))
    ffmpeg = shutil.which("ffmpeg")
    checks.append(_check("ffmpeg", "pass" if ffmpeg else "warn", f"ffmpeg found: {ffmpeg}" if ffmpeg else "ffmpeg not found; video generation will fail"))

    for module in REQUIRED_IMPORTS:
        available = importlib.util.find_spec(module) is not None
        checks.append(_check(f"python_import:{module}", "pass" if available else "fail", f"{module} import available" if available else f"required import missing: {module}"))
    for module in OPTIONAL_IMPORTS:
        available = importlib.util.find_spec(module) is not None
        checks.append(_check(f"python_import:{module}", "pass" if available else "warn", f"{module} optional import available" if available else f"optional import missing: {module}"))
    for name in CLI_FILES:
        path = paths.repo_root / name
        checks.append(_check(f"cli_file:{name}", "pass" if path.is_file() else "fail", f"{path} exists" if path.is_file() else f"missing CLI file: {path}"))

    for label, root in (("output_root", paths.output_root), ("export_root", paths.export_root)):
        try:
            root.mkdir(parents=True, exist_ok=True)
            checks.append(_check(label, "pass", f"writable local root: {root}"))
        except OSError as exc:
            checks.append(_check(label, "fail", f"cannot create local root: {exc}"))

    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", "demo_dataset/"],
            cwd=str(paths.repo_root),
            shell=False,
            check=False,
            timeout=10,
        ).returncode == 0
        checks.append(_check("demo_dataset_git", "pass" if ignored else "fail", "demo_dataset is ignored by Git" if ignored else "demo_dataset is not ignored by Git"))
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(_check("demo_dataset_git", "warn", f"could not query Git ignore status: {exc}"))

    try:
        validation = TemplateStore(paths.template_root).validate("script.default")
        checks.append(_check("templates", "pass" if validation["valid"] else "fail", "script.default template is valid" if validation["valid"] else "script.default template is invalid"))
    except Exception as exc:
        checks.append(_check("templates", "fail", f"template system unavailable: {exc}"))

    for script in HELP_SCRIPTS:
        try:
            result = subprocess.run(
                list(help_command(paths, script)),
                cwd=str(paths.repo_root),
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            status = "pass" if result.returncode == 0 else "fail"
            message = f"{script} --help passed" if status == "pass" else f"{script} --help returned {result.returncode}"
        except (OSError, subprocess.SubprocessError) as exc:
            status, message = "fail", f"{script} --help failed: {exc}"
        checks.append(_check(f"cli_help:{script}", status, message))

    warnings = [item["message"] for item in checks if item["status"] == "warn"]
    errors = [item["message"] for item in checks if item["status"] == "fail"]
    overall = "fail" if errors else "warn" if warnings else "pass"
    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "live_publishing_enabled": False,
    }


def print_health(report: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(f"Shorts Factory system health: {str(report['status']).upper()}")
    for item in report["checks"]:
        print(f"[{str(item['status']).upper()}] {item['name']}: {item['message']}")
    print("Live publishing enabled: false")
