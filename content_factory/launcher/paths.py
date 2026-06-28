from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CLI_FILES = (
    "mission_control.py",
    "orchestrator.py",
    "score_job.py",
    "phase3_audit.py",
    "export_bundle.py",
    "revise_job.py",
    "upload_kit.py",
    "template_editor.py",
)

KNOWLEDGE_FILES = (
    Path("docs/knowledge/PROJECT_STATE.md"),
    Path("docs/knowledge/ROADMAP.md"),
    Path("docs/knowledge/AUTONOMOUS_RULES.md"),
    Path("docs/audits/PHASE_3_LOCAL_OS_AUDIT.md"),
)


@dataclass(frozen=True)
class LauncherPaths:
    repo_root: Path

    @classmethod
    def default(cls) -> "LauncherPaths":
        return cls(Path(__file__).resolve().parents[2])

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", self.repo_root.expanduser().resolve())

    @property
    def output_root(self) -> Path:
        return self.repo_root / "output"

    @property
    def export_root(self) -> Path:
        return self.repo_root / "exports"

    @property
    def demo_root(self) -> Path:
        return self.repo_root / "demo_dataset"

    @property
    def template_root(self) -> Path:
        return self.repo_root / "templates"

    def script(self, name: str) -> Path:
        if name not in CLI_FILES:
            raise ValueError(f"unsupported launcher script: {name}")
        return self.repo_root / name

    def knowledge_paths(self) -> tuple[Path, ...]:
        return tuple(self.repo_root / relative for relative in KNOWLEDGE_FILES)


def latest_job_id(output_root: Path) -> str | None:
    jobs_root = output_root.expanduser().resolve() / "jobs"
    if not jobs_root.is_dir():
        return None
    candidates: list[tuple[int, str]] = []
    for directory in jobs_root.iterdir():
        receipt = directory / "receipt.json"
        if directory.is_dir() and receipt.is_file():
            try:
                candidates.append((receipt.stat().st_mtime_ns, directory.name))
            except OSError:
                continue
    return max(candidates, default=(0, ""))[1] or None


def latest_child(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    candidates = []
    for path in root.iterdir():
        if path.is_dir():
            try:
                candidates.append((path.stat().st_mtime_ns, path.name, path.resolve()))
            except OSError:
                continue
    return max(candidates, default=(0, "", None))[2]
