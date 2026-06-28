from __future__ import annotations

from typing import Iterable

from content_factory.previews.platform_rules import (
    INSTAGRAM_REELS,
    TIKTOK,
    YOUTUBE_SHORTS,
)


BANNED_TEXT_SNIPPETS = (
    "todo",
    "tbd",
    "<title>",
    "<caption>",
    "lorem ipsum",
)

PLACEHOLDER_SNIPPETS = (
    "{hook}",
    "{cta}",
    "{job_id}",
)

RISKY_PHRASES = (
    "guaranteed",
    "make money fast",
    "100% success",
    "instant results",
    "risk-free",
    "no effort",
    "medical cure",
    "legal guarantee",
    "financial advice",
)


def warning(code: str, message: str) -> dict[str, str]:
    return {"type": "local_advisory_warning", "code": code, "message": message}


def text_warning_checks(label: str, value: str) -> tuple[dict[str, str], ...]:
    lowered = value.casefold()
    warnings: list[dict[str, str]] = []
    for snippet in BANNED_TEXT_SNIPPETS:
        if snippet in lowered:
            warnings.append(
                warning(
                    f"{label}_banned_text",
                    f"{label} still contains banned placeholder text: {snippet}",
                )
            )
    for snippet in PLACEHOLDER_SNIPPETS:
        if snippet in lowered:
            warnings.append(
                warning(
                    f"{label}_template_placeholder",
                    f"{label} still contains unresolved template text: {snippet}",
                )
            )
    for phrase in RISKY_PHRASES:
        if phrase in lowered:
            warnings.append(
                warning(
                    f"{label}_risky_phrase",
                    f"{label} includes risky wording for human review: {phrase}",
                )
            )
    return tuple(warnings)


def hashtag_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in value.replace("\n", " ").split() if token)


def platform_copy_warnings(
    platform: str,
    *,
    title: str = "",
    caption: str = "",
    description: str = "",
    hashtags: Iterable[str] = (),
) -> tuple[dict[str, str], ...]:
    normalized = tuple(hashtags)
    hashtag_set = {tag.casefold() for tag in normalized}
    warnings: list[dict[str, str]] = []
    if platform == "youtube_shorts":
        if len(title) > YOUTUBE_SHORTS["title_max_chars"]:
            warnings.append(
                warning(
                    "youtube_title_too_long",
                    f"YouTube title exceeds {YOUTUBE_SHORTS['title_max_chars']} characters.",
                )
            )
        if len(description) > YOUTUBE_SHORTS["description_max_chars"]:
            warnings.append(
                warning(
                    "youtube_description_too_long",
                    f"YouTube description exceeds {YOUTUBE_SHORTS['description_max_chars']} characters.",
                )
            )
        if "#shorts" not in hashtag_set:
            warnings.append(
                warning(
                    "youtube_missing_shorts_hashtag",
                    "YouTube Shorts is missing the recommended #shorts hashtag.",
                )
            )
    elif platform == "tiktok":
        if len(caption) > TIKTOK["caption_max_chars"]:
            warnings.append(
                warning(
                    "tiktok_caption_too_long",
                    f"TikTok caption exceeds {TIKTOK['caption_max_chars']} characters.",
                )
            )
        if not normalized:
            warnings.append(
                warning(
                    "tiktok_missing_hashtags",
                    "TikTok is missing expected hashtags.",
                )
            )
    elif platform == "instagram_reels":
        if len(caption) > INSTAGRAM_REELS["caption_max_chars"]:
            warnings.append(
                warning(
                    "instagram_caption_too_long",
                    f"Instagram Reels caption exceeds {INSTAGRAM_REELS['caption_max_chars']} characters.",
                )
            )
        if len(normalized) > INSTAGRAM_REELS["recommended_max_hashtags"]:
            warnings.append(
                warning(
                    "instagram_too_many_hashtags",
                    f"Instagram Reels exceeds {INSTAGRAM_REELS['recommended_max_hashtags']} hashtags.",
                )
            )
    else:
        raise ValueError(f"unsupported compliance platform: {platform}")
    return tuple(warnings)
