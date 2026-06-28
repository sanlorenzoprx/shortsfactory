from __future__ import annotations

from collections.abc import Callable

from .command_runner import (
    CommandRunner,
    audit_command,
    generate_api_command,
    generate_mock_command,
    mission_control_command,
    score_command,
)
from .health_check import print_health, run_health_check
from .paths import LauncherPaths, latest_child, latest_job_id


MENU = """Shorts Factory Local Launcher

1. Start Mission Control
2. Generate new mock short
3. Generate new API short
4. Score latest job
5. Run Phase 3 audit
6. Open docs/knowledge
7. Open latest export/upload kit folder
8. Check system health
9. Exit"""


def render_menu() -> str:
    return MENU


def print_knowledge_paths(paths: LauncherPaths) -> None:
    print("\nLocal documentation:")
    for path in paths.knowledge_paths():
        status = "exists" if path.is_file() else "missing"
        print(f"- {path} ({status})")


def print_latest_artifact_paths(paths: LauncherPaths) -> None:
    approved = latest_child(paths.export_root / "approved")
    upload_kit = latest_child(paths.export_root / "upload_kits")
    print("\nLatest local export/upload-kit folders:")
    print(f"- Approved export: {approved or 'not available'}")
    print(f"- Manual upload kit: {upload_kit or 'not available'}")


def run_menu(
    paths: LauncherPaths | None = None,
    *,
    input_function: Callable[[str], str] = input,
    runner: CommandRunner | None = None,
) -> int:
    paths = paths or LauncherPaths.default()
    runner = runner or CommandRunner(paths)
    while True:
        print(f"\n{render_menu()}")
        try:
            choice = input_function("\nChoose an action: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLauncher closed.")
            return 0
        if choice == "1":
            print("Mission Control URL: http://127.0.0.1:8765")
            runner.run(mission_control_command(paths))
        elif choice == "2":
            runner.run(generate_mock_command(paths))
        elif choice == "3":
            runner.run(generate_api_command(paths))
        elif choice == "4":
            job_id = latest_job_id(paths.output_root)
            if job_id is None:
                print("No receipt-backed job is available to score.")
            else:
                runner.run(score_command(paths, job_id))
        elif choice == "5":
            runner.run(audit_command(paths))
        elif choice == "6":
            print_knowledge_paths(paths)
        elif choice == "7":
            print_latest_artifact_paths(paths)
        elif choice == "8":
            print_health(run_health_check(paths))
        elif choice == "9":
            print("Launcher closed.")
            return 0
        else:
            print("Choose a number from 1 to 9.")
