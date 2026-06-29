from __future__ import annotations

import argparse
import sys
from typing import Sequence

from content_factory.performance import PerformanceReviewError, PerformanceReviewStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic local performance review from manually entered results only."
    )
    parser.add_argument("--results-root", default="results_ledger", help="Local manual results ledger root")
    parser.add_argument("--output-root", default="performance_reports", help="Local performance report output root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = PerformanceReviewStore(args.results_root, args.output_root)
    try:
        result = store.generate()
    except (PerformanceReviewError, OSError) as exc:
        print(f"Performance review refused: {exc}", file=sys.stderr)
        return 1
    print(f"Performance review status: {result.review['status']}")
    for path in result.paths.values():
        print(path)
    print("Manual results only. No API fetch, upload, scraping, or live publishing occurred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
