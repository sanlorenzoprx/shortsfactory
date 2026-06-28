from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from content_factory.templates import TemplateRenderError, TemplateStore, TemplateStoreError, render_template

SAMPLE_CONTEXT: dict[str, Any] = {
    "job_id": "sample", "idea": "AI tool that tests startup ideas before builders waste months",
    "hook": "Would this idea survive the ghost town test?", "verdict_headline": "Promising, but distribution is the risk",
    "lit_score": 78, "risk_level": "medium", "top_reason": "The pain is real, but the buyer path needs proof.",
    "next_step": "Test one landing page with ten builders.", "source": "sample",
    "cta": "Run your idea through the test before you build.", "created_at": "2026-06-28T00:00:00+00:00",
    "locale": "en-US", "platform": "youtube_shorts", "hashtags": "#shorts #startup #ideavalidation",
    "title": "Would this idea survive?", "caption": "Promising, but distribution is the risk.",
    "description": "A deterministic sample description.", "revision_note": "Make the hook clearer.",
    "original_job_id": "sample-original", "quality_score": 88, "quality_status": "pass", "recommended_action": "approve",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="View and validate local text-only Shorts Factory templates.")
    parser.add_argument("--template-root", default="templates", help="Local editable template root")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="List built-in and local templates")
    actions.add_argument("--show", metavar="TEMPLATE_ID", help="Print the current template JSON")
    actions.add_argument("--validate", metavar="TEMPLATE_ID", help="Validate one template")
    actions.add_argument("--preview", metavar="TEMPLATE_ID", help="Render one template with fixed sample data")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = TemplateStore(args.template_root)
    try:
        if args.list:
            for item in store.list():
                valid = "valid" if item["validation"]["valid"] else "invalid"
                print(f"{item['template_id']}\t{item['template_type']}\tv{item['version']}\t{item['source']}\t{valid}")
            return 0
        template_id = args.show or args.validate or args.preview
        template = store.get(template_id)
        if template is None:
            raise TemplateStoreError(f"template not found: {template_id}")
        if args.show:
            print(json.dumps(template, indent=2, ensure_ascii=False))
        elif args.validate:
            result = store.validate(template_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["valid"] else 1
        else:
            rendered = render_template(template, SAMPLE_CONTEXT)
            print("\n".join(rendered) if isinstance(rendered, list) else rendered)
        return 0
    except (TemplateStoreError, TemplateRenderError, OSError) as exc:
        print(f"Template operation refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
