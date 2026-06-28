from __future__ import annotations

from pathlib import Path

from content_factory.templates import TemplateRenderError, TemplateStore, render_template


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

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.
""",
    "tiktok": """# TikTok Manual Upload Checklist

- [ ] Confirm this is the approved final.mp4.
- [ ] Upload manually in TikTok.
- [ ] Paste caption.txt.
- [ ] Add hashtags from hashtags.txt.
- [ ] Confirm cover frame manually.
- [ ] Confirm no private/internal information is visible.
- [ ] Publish manually only after final human review.

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.
""",
    "instagram_reels": """# Instagram Reels Manual Upload Checklist

- [ ] Confirm this is the approved final.mp4.
- [ ] Upload manually in Instagram.
- [ ] Paste caption.txt.
- [ ] Add hashtags from hashtags.txt.
- [ ] Select cover manually.
- [ ] Confirm no private/internal information is visible.
- [ ] Publish manually only after final human review.

Status: DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY.
""",
}


def build_checklist_details(platform: str, template_root: str | Path = "templates", job_id: str = "") -> tuple[str, dict[str, str] | None, str | None]:
    try:
        fallback = CHECKLISTS[platform]
    except KeyError as exc:
        raise ValueError(f"unsupported checklist platform: {platform}") from exc
    template_id = f"upload_checklist.{platform}"
    template = TemplateStore(template_root).get(template_id)
    if template is None:
        return fallback, None, f"{template_id} missing or unreadable; deterministic fallback used"
    try:
        rendered = render_template(template, {"job_id": job_id, "platform": platform})
        text = "\n".join(rendered) if isinstance(rendered, list) else rendered
        usage = {"template_id": template_id, "template_version_hash": str(template["template_version_hash"]), "source": "local_template"}
        return text, usage, None
    except (TemplateRenderError, KeyError, TypeError, ValueError) as exc:
        return fallback, None, f"{template_id} invalid; deterministic fallback used: {exc}"


def build_checklist(platform: str, template_root: str | Path = "templates", job_id: str = "") -> str:
    return build_checklist_details(platform, template_root, job_id)[0]
