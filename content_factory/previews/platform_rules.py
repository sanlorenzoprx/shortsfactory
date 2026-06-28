from __future__ import annotations

from typing import Any


YOUTUBE_SHORTS = {
    "title_max_chars": 100,
    "description_max_chars": 5000,
    "recommended_hashtags": ("#shorts",),
}
TIKTOK = {"caption_max_chars": 2200, "recommended_min_hashtags": 1}
INSTAGRAM_REELS = {"caption_max_chars": 2200, "recommended_max_hashtags": 30}


def advisory(code: str, message: str) -> dict[str, str]:
    return {"type": "local_advisory_warning", "code": code, "message": message}


def platform_warnings(
    platform: str,
    *,
    title: str = "",
    caption: str = "",
    description: str = "",
    hashtags: tuple[str, ...] = (),
    final_video_present: bool = True,
    manual_upload_only: bool = True,
) -> tuple[dict[str, str], ...]:
    warnings: list[dict[str, str]] = []
    if not final_video_present:
        warnings.append(advisory("missing_final_video", "final.mp4 is missing."))
    if not manual_upload_only:
        warnings.append(advisory("missing_manual_upload_flag", "Manual-upload-only status is missing."))
    normalized = {tag.casefold() for tag in hashtags}
    if platform == "youtube_shorts":
        if len(title) > YOUTUBE_SHORTS["title_max_chars"]:
            warnings.append(advisory("title_too_long", f"Title exceeds {YOUTUBE_SHORTS['title_max_chars']} characters."))
        if len(description) > YOUTUBE_SHORTS["description_max_chars"]:
            warnings.append(advisory("description_too_long", f"Description exceeds {YOUTUBE_SHORTS['description_max_chars']} characters."))
        if "#shorts" not in normalized:
            warnings.append(advisory("missing_shorts_hashtag", "Recommended local advisory: add #shorts."))
    elif platform == "tiktok":
        if len(caption) > TIKTOK["caption_max_chars"]:
            warnings.append(advisory("caption_too_long", f"Caption exceeds {TIKTOK['caption_max_chars']} characters."))
        if len(hashtags) < TIKTOK["recommended_min_hashtags"]:
            warnings.append(advisory("missing_hashtags", "Recommended local advisory: add at least one hashtag."))
    elif platform == "instagram_reels":
        if len(caption) > INSTAGRAM_REELS["caption_max_chars"]:
            warnings.append(advisory("caption_too_long", f"Caption exceeds {INSTAGRAM_REELS['caption_max_chars']} characters."))
        if len(hashtags) > INSTAGRAM_REELS["recommended_max_hashtags"]:
            warnings.append(advisory("too_many_hashtags", f"Hashtag count exceeds {INSTAGRAM_REELS['recommended_max_hashtags']}."))
    else:
        raise ValueError(f"unsupported preview platform: {platform}")
    return tuple(warnings)
