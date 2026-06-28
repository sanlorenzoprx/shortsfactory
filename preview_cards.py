from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from content_factory.previews import PreviewCardError, generate_preview_cards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate static local publisher preview cards from an approved manual upload kit.")
    parser.add_argument("--job-id", required=True, help="Approved exported job ID")
    parser.add_argument("--export-root", default="exports", help="Local export root")
    parser.add_argument("--json", action="store_true", help="Print the preview manifest JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = generate_preview_cards(args.job_id, args.export_root)
    except (PreviewCardError, OSError) as exc:
        print(f"Preview generation refused: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.manifest, indent=2, ensure_ascii=False))
    else:
        print(f"Preview cards generated: {result.preview_dir}")
        print("Platforms: youtube_shorts, tiktok, instagram_reels")
        print("Status: MANUAL REVIEW ONLY - NOT PUBLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
