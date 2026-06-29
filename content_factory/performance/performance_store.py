from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_factory.mission_control.job_index import is_within

from .performance_loader import PerformanceReviewError, load_manual_results
from .performance_metrics import build_performance_review
from .performance_models import JOB_CSV, PLATFORM_CSV, REPORT_JSON, REPORT_MARKDOWN, TEMPLATE_CSV
from .performance_report import render_job_csv, render_markdown, render_platform_csv, render_template_csv


@dataclass(frozen=True)
class PerformanceReviewResult:
    review: dict[str, Any]
    paths: dict[str, Path]


class PerformanceReviewStore:
    def __init__(self, results_root: str | Path = "results_ledger", output_root: str | Path = "performance_reports"):
        self.results_root = Path(results_root).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()

    def path(self, filename: str) -> Path:
        if Path(filename).name != filename:
            raise PerformanceReviewError("performance report filename is invalid")
        path = self.output_root / filename
        if not is_within(path, self.output_root):
            raise PerformanceReviewError("performance report path escapes output root")
        return path

    def preview(self) -> dict[str, Any]:
        return build_performance_review(load_manual_results(self.results_root), results_root=self.results_root)

    def _atomic_write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".performance.", suffix=".tmp", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(value)
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def generate(self) -> PerformanceReviewResult:
        review = self.preview()
        paths = {
            "markdown": self.path(REPORT_MARKDOWN),
            "json": self.path(REPORT_JSON),
            "platform_csv": self.path(PLATFORM_CSV),
            "template_csv": self.path(TEMPLATE_CSV),
            "job_csv": self.path(JOB_CSV),
        }
        values = {
            "markdown": render_markdown(review).rstrip() + "\n",
            "json": json.dumps(review, indent=2, ensure_ascii=False) + "\n",
            "platform_csv": render_platform_csv(review),
            "template_csv": render_template_csv(review),
            "job_csv": render_job_csv(review),
        }
        for name, path in paths.items():
            self._atomic_write(path, values[name])
        return PerformanceReviewResult(review=review, paths=paths)

    def read_markdown(self) -> str:
        path = self.path(REPORT_MARKDOWN)
        if not path.is_file():
            raise PerformanceReviewError("performance report has not been generated")
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PerformanceReviewError("performance report is unreadable") from exc

    def report_exists(self) -> bool:
        return self.path(REPORT_MARKDOWN).is_file()
