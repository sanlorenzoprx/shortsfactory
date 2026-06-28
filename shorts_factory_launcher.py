from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from content_factory.launcher.command_runner import (
    CommandRunner,
    audit_command,
    generate_api_command,
    generate_mock_command,
    mission_control_command,
)
from content_factory.launcher.health_check import print_health, run_health_check
from content_factory.launcher.launcher_menu import run_menu
from content_factory.launcher.paths import LauncherPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the safe local Shorts Factory operator launcher."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root (default: directory containing this launcher)",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--health", action="store_true", help="Run local dependency and CLI health checks")
    actions.add_argument("--start-mission-control", action="store_true", help="Start Mission Control on 127.0.0.1")
    actions.add_argument("--run-audit", action="store_true", help="Run the local Phase 3 audit")
    actions.add_argument("--generate-mock", action="store_true", help="Generate one local mock short")
    actions.add_argument("--generate-api", action="store_true", help="Generate one API-mode short with existing fallback behavior")
    parser.add_argument("--json", action="store_true", help="Print health results as JSON (with --health)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = (
        LauncherPaths(Path(args.repo_root))
        if args.repo_root
        else LauncherPaths.default()
    )
    if args.json and not args.health:
        build_parser().error("--json requires --health")
    if args.health:
        report = run_health_check(paths)
        print_health(report, as_json=args.json)
        return 1 if report["status"] == "fail" else 0
    runner = CommandRunner(paths)
    if args.start_mission_control:
        print("Mission Control URL: http://127.0.0.1:8765")
        return runner.run(mission_control_command(paths))
    if args.run_audit:
        return runner.run(audit_command(paths))
    if args.generate_mock:
        return runner.run(generate_mock_command(paths))
    if args.generate_api:
        return runner.run(generate_api_command(paths))
    return run_menu(paths, runner=runner)


if __name__ == "__main__":
    raise SystemExit(main())
