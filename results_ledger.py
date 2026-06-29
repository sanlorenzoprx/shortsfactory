from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from content_factory.results import ResultsLedgerError, ResultsLedgerStore
from content_factory.results.result_models import ALLOWED_PLATFORMS, METRIC_FIELDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record and inspect local manual upload results without calling any platform APIs."
    )
    parser.add_argument("--ledger-root", default="results_ledger", help="Local results ledger root")
    parser.add_argument("--export-root", default="exports", help="Local export root")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    actions = parser.add_mutually_exclusive_group(required=False)
    actions.add_argument("--list", action="store_true", help="List recorded manual results")
    actions.add_argument("--summary", action="store_true", help="Print the manual results summary")
    actions.add_argument("--show", metavar="ENTRY_ID", help="Show one result entry as JSON")
    actions.add_argument("--update", metavar="ENTRY_ID", help="Update one existing result entry")
    parser.add_argument("--job-id", help="Ready-for-manual-upload job ID")
    parser.add_argument("--platform", help=f"Platform: {', '.join(ALLOWED_PLATFORMS)}")
    parser.add_argument("--url", help="Manually pasted https:// upload URL")
    parser.add_argument("--notes", default="", help="Local operator notes")
    for field in METRIC_FIELDS:
        parser.add_argument(f"--{field}", type=int, help=f"{field.title()} count")
    return parser


def _metrics_from_args(args: argparse.Namespace) -> dict[str, int]:
    return {
        field: int(getattr(args, field))
        for field in METRIC_FIELDS
        if getattr(args, field) is not None
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ResultsLedgerStore(
        args.ledger_root,
        export_root=args.export_root,
        output_root=args.output_root,
    )
    try:
        if args.list:
            entries = store.list_entries()
            if not entries:
                print("No manual results recorded.")
            else:
                for entry in entries:
                    metrics = entry.get("metrics", {})
                    print(
                        f"{entry['entry_id']} | {entry['job_id']} | {entry['platform']} | "
                        f"views={metrics.get('views', 0)} likes={metrics.get('likes', 0)} "
                        f"leads={metrics.get('leads', 0)}"
                    )
            return 0
        if args.summary:
            print(store.summary_text().rstrip())
            return 0
        if args.show:
            print(json.dumps(store.read_entry(args.show), indent=2, ensure_ascii=False))
            return 0
        if args.update:
            result = store.update_result(
                args.update,
                metrics=_metrics_from_args(args),
                notes=args.notes if args.notes != "" else None,
            )
            print(json.dumps(result.entry, indent=2, ensure_ascii=False))
            return 0
        if not args.job_id or not args.platform or not args.url:
            build_parser().error("--job-id, --platform, and --url are required unless using --list, --summary, --show, or --update")
        result = store.record_result(
            job_id=args.job_id,
            platform=args.platform,
            manual_upload_url=args.url,
            metrics=_metrics_from_args(args),
            notes=args.notes,
        )
    except (ResultsLedgerError, OSError) as exc:
        print(f"Results ledger refused: {exc}", file=sys.stderr)
        return 1
    print(f"Results entry recorded: {result.entry['entry_id']}")
    print(f"Ledger: {store._ledger_path()}")
    print(f"Summary: {result.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
