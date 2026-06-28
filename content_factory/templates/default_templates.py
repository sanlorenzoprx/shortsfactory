from __future__ import annotations

from copy import deepcopy
from typing import Any

from .template_model import template_hash

BUILTIN_TIMESTAMP = "2026-06-28T00:00:00+00:00"


def _template(template_id: str, template_type: str, name: str, description: str, content: str | list[str], required: list[str], optional: list[str] | None = None, *, max_lines: int = 40, max_chars: int = 500, locked: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "template_id": template_id,
        "template_type": template_type,
        "name": name,
        "description": description,
        "version": 1,
        "created_at": BUILTIN_TIMESTAMP,
        "updated_at": BUILTIN_TIMESTAMP,
        "content": content,
        "required_placeholders": required,
        "optional_placeholders": optional or [],
        "max_lines": max_lines,
        "max_chars_per_line": max_chars,
        "enabled": True,
        "locked": locked,
    }
    value["template_version_hash"] = template_hash(value)
    return value


CHECKLISTS = {
    "youtube_shorts": """# YouTube Shorts Manual Upload Checklist

- [ ] Confirm this is the approved final.mp4.
- [ ] Confirm the video is vertical 9:16.
- [ ] Upload final.mp4 manually in YouTube Studio.
- [ ] Paste title.txt.
- [ ] Paste description.txt.
- [ ] Add hashtags from hashtags.txt.
- [ ] Add captions.srt if desired/available.
- [ ] Confirm visibility setting intentionally.
- [ ] Confirm no private/internal information is visible.
- [ ] Publish manually only after final human review.

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.""",
    "tiktok": """# TikTok Manual Upload Checklist

- [ ] Confirm this is the approved final.mp4.
- [ ] Upload manually in TikTok.
- [ ] Paste caption.txt.
- [ ] Add hashtags from hashtags.txt.
- [ ] Confirm cover frame manually.
- [ ] Confirm no private/internal information is visible.
- [ ] Publish manually only after final human review.

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.""",
    "instagram_reels": """# Instagram Reels Manual Upload Checklist

- [ ] Confirm this is the approved final.mp4.
- [ ] Upload manually in Instagram.
- [ ] Paste caption.txt.
- [ ] Add hashtags from hashtags.txt.
- [ ] Select cover manually.
- [ ] Confirm no private/internal information is visible.
- [ ] Publish manually only after final human review.

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.""",
}

BUILTIN_TEMPLATES = {
    "script.default": _template(
        "script.default", "script", "Default LIT Script",
        "Default short-form script template for LIT verdict videos.",
        ["{hook}", "Score: {lit_score}/100.", "Main risk: {risk_level}.", "{top_reason}", "Verdict: {verdict_headline}.", "{cta}"],
        ["hook", "lit_score", "risk_level", "top_reason", "verdict_headline", "cta"],
        ["idea", "next_step", "locale"], max_lines=8, max_chars=120,
    ),
    "caption.default": _template(
        "caption.default", "caption", "Default Caption Text",
        "Text layout used as a safe caption-formatting reference.",
        "{caption}", ["caption"], ["hook", "top_reason", "cta", "locale"], max_lines=20, max_chars=300,
    ),
    "thumbnail.default": _template(
        "thumbnail.default", "thumbnail", "Default Thumbnail Text",
        "Text-only thumbnail copy; image drawing remains deterministic Python.",
        ["{title}", "{idea}", "{lit_score}/100", "{verdict_headline}", "{cta}"],
        ["title", "idea", "lit_score", "verdict_headline", "cta"], ["locale"], max_lines=8, max_chars=80,
    ),
    "revision.default": _template(
        "revision.default", "revision", "Default Revision Note",
        "Text appended when no named deterministic revision rule matches.",
        "Revision focus: {revision_note}", ["revision_note"], ["original_job_id", "locale"], max_lines=4, max_chars=180,
    ),
    "quality_message.default": _template(
        "quality_message.default", "quality_message", "Quality Status Message",
        "Local quality summary wording.",
        "Quality: {quality_score}/100 ({quality_status}). Recommended action: {recommended_action}.",
        ["quality_score", "quality_status", "recommended_action"], max_lines=3, max_chars=180, locked=True,
    ),
}

for _platform in ("youtube_shorts", "tiktok", "instagram_reels"):
    _metadata_field = "description" if _platform == "youtube_shorts" else "caption"
    BUILTIN_TEMPLATES[f"publisher_metadata.{_platform}"] = _template(
        f"publisher_metadata.{_platform}", "publisher_metadata", f"{_platform.replace('_', ' ').title()} Metadata",
        "Text-only platform caption/description format.", f"{{{_metadata_field}}}",
        [_metadata_field], ["title", "description", "caption", "hashtags", "platform"], max_lines=40, max_chars=500,
    )
    BUILTIN_TEMPLATES[f"upload_checklist.{_platform}"] = _template(
        f"upload_checklist.{_platform}", "upload_checklist", f"{_platform.replace('_', ' ').title()} Upload Checklist",
        "Manual-only upload checklist wording.", CHECKLISTS[_platform], [], ["job_id", "platform"], max_lines=40, max_chars=500,
    )


def builtin_templates() -> dict[str, dict[str, Any]]:
    return deepcopy(BUILTIN_TEMPLATES)
