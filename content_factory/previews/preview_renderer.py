from __future__ import annotations

import json

from .html_escape import escape_html
from .preview_models import PlatformPreview, SAFETY_FLAGS


def _warning_lines(preview: PlatformPreview) -> str:
    if not preview.warnings:
        return "- None"
    return "\n".join(
        f"- [{warning['type']}] {warning['code']}: {warning['message']}"
        for warning in preview.warnings
    )


def render_text(preview: PlatformPreview) -> str:
    copy_label = "Title" if preview.platform == "youtube_shorts" else "Caption"
    copy_value = preview.title if preview.platform == "youtube_shorts" else preview.caption
    description = f"\nDescription:\n{preview.description}\n" if preview.description else ""
    return f"""{preview.display_name.upper()} MANUAL UPLOAD PREVIEW

Platform:
{preview.display_name}

Video:
{preview.video_path}

Thumbnail:
{preview.thumbnail_path or 'Not available'}

{copy_label}:
{copy_value}
{description}
Hashtags:
{' '.join(preview.hashtags) or 'None'}

Character counts:
- title: {len(preview.title)}
- caption: {len(preview.caption)}
- description: {len(preview.description)}
- hashtags: {len(preview.hashtags)}

Checklist:
{preview.checklist}

Warnings:
{_warning_lines(preview)}

Safety:
manual_upload_only: true
publishing_status: not_published
live_publishing_enabled: false
api_upload_attempted: false
requires_human_upload: true
"""


def render_html(preview: PlatformPreview) -> str:
    copy_label = "Title" if preview.platform == "youtube_shorts" else "Caption"
    copy_value = preview.title if preview.platform == "youtube_shorts" else preview.caption
    warnings = (
        "".join(
            f"<li><strong>{escape_html(item['type'])}</strong> — {escape_html(item['message'])}</li>"
            for item in preview.warnings
        )
        or "<li>None</li>"
    )
    description = (
        f"<section><h2>Description</h2><pre>{escape_html(preview.description)}</pre></section>"
        if preview.description
        else ""
    )
    safety = escape_html(json.dumps(SAFETY_FLAGS, indent=2, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape_html(preview.display_name)} Manual Preview</title>
<style>body{{margin:0;background:#0a0d10;color:#eef3ef;font:15px/1.55 system-ui,sans-serif}}main{{max-width:760px;margin:auto;padding:32px}}.card{{background:#141a20;border:1px solid #2b343d;border-radius:16px;padding:24px}}.badge{{display:inline-block;background:#ffcb66;color:#111;padding:5px 9px;font-weight:800}}h1,h2{{margin-bottom:8px}}pre{{white-space:pre-wrap;word-break:break-word;background:#090c0f;padding:14px;border-radius:8px}}code{{word-break:break-all;color:#73e6e9}}li{{margin:6px 0}}.counts{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.counts div{{background:#090c0f;padding:10px}}</style>
</head><body><main><article class="card"><span class="badge">MANUAL UPLOAD ONLY — NOT PUBLISHED</span>
<h1>{escape_html(preview.display_name)} Preview</h1>
<p><strong>Video:</strong> <code>{escape_html(preview.video_path)}</code></p>
<p><strong>Thumbnail:</strong> <code>{escape_html(preview.thumbnail_path or 'Not available')}</code></p>
<section><h2>{copy_label}</h2><pre>{escape_html(copy_value)}</pre></section>{description}
<section><h2>Hashtags</h2><pre>{escape_html(' '.join(preview.hashtags) or 'None')}</pre></section>
<section><h2>Character counts</h2><div class="counts"><div>Title<br><strong>{len(preview.title)}</strong></div><div>Caption<br><strong>{len(preview.caption)}</strong></div><div>Description<br><strong>{len(preview.description)}</strong></div><div>Hashtags<br><strong>{len(preview.hashtags)}</strong></div></div></section>
<section><h2>Checklist</h2><pre>{escape_html(preview.checklist)}</pre></section>
<section><h2>Local advisory warnings</h2><ul>{warnings}</ul></section>
<section><h2>Safety</h2><pre>{safety}</pre></section>
</article></main></body></html>"""
