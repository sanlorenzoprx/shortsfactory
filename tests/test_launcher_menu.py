from __future__ import annotations

from pathlib import Path

from content_factory.launcher.launcher_menu import render_menu, run_menu
from content_factory.launcher.paths import LauncherPaths


EXPECTED_OPTIONS = (
    "Start Mission Control",
    "Generate new mock short",
    "Generate new API short",
    "Score latest job",
    "Run Phase 3 audit",
    "Open docs/knowledge",
    "Open latest export/upload kit folder",
    "Check system health",
    "Exit",
)


def test_menu_renders_all_expected_options_without_posting_actions():
    menu = render_menu()
    assert all(option in menu for option in EXPECTED_OPTIONS)
    lowered = menu.casefold()
    for forbidden in ("publish to", "auto-post", "connect account", "oauth login"):
        assert forbidden not in lowered


def test_menu_exit_is_clean_and_runs_no_command(tmp_path: Path):
    class RefusingRunner:
        def run(self, _command):
            raise AssertionError("exit must not run a command")

    answers = iter(["9"])
    result = run_menu(
        LauncherPaths(tmp_path),
        input_function=lambda _prompt: next(answers),
        runner=RefusingRunner(),
    )
    assert result == 0


def test_menu_handles_end_of_input_cleanly(tmp_path: Path):
    def end(_prompt: str) -> str:
        raise EOFError

    assert run_menu(LauncherPaths(tmp_path), input_function=end) == 0
