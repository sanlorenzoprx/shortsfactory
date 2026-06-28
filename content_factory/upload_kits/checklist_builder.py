from __future__ import annotations


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


def build_checklist(platform: str) -> str:
    try:
        return CHECKLISTS[platform]
    except KeyError as exc:
        raise ValueError(f"unsupported checklist platform: {platform}") from exc
