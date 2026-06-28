from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from content_factory.compliance import (
    ComplianceChecklistError,
    generate_compliance_checklist,
    mark_compliance_reviewed,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or confirm the final local compliance checklist before manual upload."
    )
    parser.add_argument("--job-id", required=True, help="Approved exported job ID")
    parser.add_argument("--export-root", default="exports", help="Local export root")
    parser.add_argument("--mark-reviewed", action="store_true", help="Mark all human review items complete after machine checks pass")
    parser.add_argument("--json", action="store_true", help="Print the compliance checklist JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = (
            mark_compliance_reviewed(args.job_id, args.export_root)
            if args.mark_reviewed
            else generate_compliance_checklist(args.job_id, args.export_root)
        )
    except (ComplianceChecklistError, OSError) as exc:
        print(f"Compliance check refused: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.checklist, indent=2, ensure_ascii=False))
    else:
        print(f"Compliance checklist written: {result.compliance_dir}")
        print(f"Status: {result.checklist['status']}")
        print(f"Ready for manual upload: {str(result.checklist['ready_for_manual_upload']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
