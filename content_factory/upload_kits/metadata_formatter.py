from __future__ import annotations

import re
from typing import Any

from .platform_profiles import PlatformProfile


DEFAULT_HASHTAGS = ("#shorts", "#startup", "#buildinpublic", "#businessideas", "#aitools")
LIT_HASHTAGS = ("#ideavalidation", "#founder", "#builders", "#productivity")
FALLBACK_CAPTION = "A quick builder idea test from Shorts Factory."


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _truncate(value: str, limit: int) -> str:
    value = _clean(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip(" ,.;:-") + "…"


def _platform_publisher_text(package: dict[str, Any], platform: str) -> str:
    candidates: list[Any] = [package.get(platform)]
    platforms = package.get("platforms")
    if isinstance(platforms, dict):
        candidates.append(platforms.get(platform))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("caption", "description", "text", "post_text"):
            if candidate.get(key):
                return _clean(candidate[key])
    for key in ("caption", "description", "text", "post_text"):
        if package.get(key):
            return _clean(package[key])
    return ""


def _verdict(receipt: dict[str, Any]) -> dict[str, Any]:
    value = receipt.get("verdict")
    return value if isinstance(value, dict) else {}


def _script_lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def build_hashtags(profile: PlatformProfile, receipt: dict[str, Any], script: str) -> list[str]:
    combined = f"{script} {receipt.get('idea', '')} {_verdict(receipt)}".casefold()
    tags = list(DEFAULT_HASHTAGS)
    if any(token in combined for token in ("ghost town", "lit", "idea", "verdict", "score")):
        tags.extend(LIT_HASHTAGS)
    unique: list[str] = []
    for tag in tags:
        normalized = "#shorts" if tag.casefold() == "#shorts" else tag.casefold()
        if normalized not in unique:
            unique.append(normalized)
    return unique[: profile.hashtag_cap]


def format_platform_copy(
    profile: PlatformProfile,
    receipt: dict[str, Any],
    script: str,
    publisher_package: dict[str, Any],
) -> dict[str, Any]:
    verdict = _verdict(receipt)
    lines = _script_lines(script)
    headline = _clean(verdict.get("verdict_headline"))
    hook = lines[0] if lines else ""
    summary = headline or hook or FALLBACK_CAPTION
    cta = lines[-1] if lines else ""
    publisher_text = _platform_publisher_text(publisher_package, profile.key)
    if publisher_text:
        caption = publisher_text
    elif cta and _clean(cta).casefold() != _clean(summary).casefold():
        caption = f"{summary} {cta}"
    elif lines:
        caption = " ".join(lines[:4])
    else:
        caption = FALLBACK_CAPTION
    caption = _truncate(caption, profile.caption_max)
    hashtags = build_hashtags(profile, receipt, script)
    title_source = headline or hook or FALLBACK_CAPTION
    title = re.sub(r"(?:^|\s)#[\w-]+", "", title_source).strip()
    title = _truncate(title, 80) if profile.has_title else ""
    description = ""
    if profile.has_description:
        description_parts = [_clean(summary)]
        if cta and _clean(cta).casefold() != _clean(summary).casefold():
            description_parts.append(_clean(cta))
        description_parts.append(" ".join(hashtags))
        description = "\n\n".join(part for part in description_parts if part)
    return {
        "title": title,
        "caption": caption,
        "description": description,
        "hashtags": hashtags,
    }
