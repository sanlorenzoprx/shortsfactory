from __future__ import annotations

from pathlib import Path
from typing import Any

from content_factory.results import ResultsLedgerError, ResultsLedgerStore


class PerformanceReviewError(RuntimeError):
    """Safe local performance-review failure."""


def load_manual_results(results_root: str | Path) -> list[dict[str, Any]]:
    """Load only validated, manually entered local ledger entries."""
    try:
        return ResultsLedgerStore(results_root).list_entries()
    except (ResultsLedgerError, OSError) as exc:
        raise PerformanceReviewError(f"manual results ledger is invalid: {exc}") from exc
