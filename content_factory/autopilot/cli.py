from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .autopilot_config import AutopilotConfig, AutopilotRefusal
from .autopilot_runner import AutopilotRunner
from .autopilot_store import AutopilotStore, AutopilotStoreError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 5A receipt-driven autopilot dry-run pipeline.")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a complete autopilot cycle")
    run.add_argument("--mode", choices=("dry_run", "supervised_autopilot", "full_autopilot"), default="dry_run")
    run.add_argument("--trend-query", default="hottest searched business ideas")
    run.add_argument("--trend-file")
    run.add_argument("--batch-size", type=int, default=3)
    run.add_argument("--locale", default="en-US")
    run.add_argument("--market", default="US")
    run.add_argument("--lit-mode", choices=("mock", "api"), default="mock")
    run.add_argument("--quality-threshold", type=int, default=80)
    run.add_argument("--output-root", dest="output_root", default=argparse.SUPPRESS)
    for name in ("status", "show", "inspect", "resume", "next-plan", "next-batch"):
        command = subparsers.add_parser(name)
        command.add_argument("--batch-id", "--run-id", dest="batch_id", required=True)
        command.add_argument("--output-root", dest="output_root", default=argparse.SUPPRESS)
    list_command = subparsers.add_parser("list", help="List local autopilot batches")
    list_command.add_argument("--output-root", dest="output_root", default=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AutopilotStore(args.output_root)
    try:
        if args.command == "run":
            config = AutopilotConfig(
                mode=args.mode, output_root=Path(args.output_root), trend_query=args.trend_query,
                trend_file=Path(args.trend_file) if args.trend_file else None,
                trend_provider="file" if args.trend_file else "mock",
                batch_size=args.batch_size, trend_limit=args.batch_size,
                locale=args.locale, market=args.market, lit_mode=args.lit_mode,
                minimum_quality_score=args.quality_threshold,
            )
            receipt = AutopilotRunner(store=store).run_cycle(config)
            print(f"Batch ID: {receipt['batch_id']}")
            print(f"Status: {receipt['status']}")
            print(f"Receipt: {store.path(receipt['batch_id'], 'receipt')}")
            print(f"Next plan: {store.path(receipt['batch_id'], 'next_plan')}")
            return 0
        if args.command == "list":
            print(json.dumps(store.list_batches(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "resume":
            receipt = AutopilotRunner(store=store).resume(args.batch_id)
            print(json.dumps(receipt, indent=2, ensure_ascii=False))
            return 0
        if args.command == "status":
            source = store.read(args.batch_id, "receipt") if store.exists(args.batch_id, "receipt") else store.read(args.batch_id, "plan")
            print(json.dumps({key: source.get(key) for key in ("batch_id", "mode", "status", "created_at", "completed_at", "counts") if key in source}, indent=2))
            return 0
        if args.command in {"next-plan", "next-batch"}:
            print(json.dumps(store.read(args.batch_id, "next_plan"), indent=2, ensure_ascii=False))
            return 0
        print(json.dumps({
            "plan": store.read(args.batch_id, "plan"),
            "receipt": store.read(args.batch_id, "receipt") if store.exists(args.batch_id, "receipt") else None,
        }, indent=2, ensure_ascii=False))
        return 0
    except (AutopilotRefusal, AutopilotStoreError, ValueError, OSError) as exc:
        print(f"Autopilot refused: {exc}", file=sys.stderr)
        return 1
