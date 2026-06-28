from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformProfile:
    key: str
    display_name: str
    hashtag_cap: int
    caption_max: int
    has_title: bool = False
    has_description: bool = False


PLATFORM_PROFILES = {
    "youtube_shorts": PlatformProfile(
        "youtube_shorts", "YouTube Shorts", 8, 500, has_title=True, has_description=True
    ),
    "tiktok": PlatformProfile("tiktok", "TikTok", 6, 220),
    "instagram_reels": PlatformProfile("instagram_reels", "Instagram Reels", 10, 300),
}
PLATFORM_ORDER = tuple(PLATFORM_PROFILES)


def selected_platforms(value: str) -> tuple[PlatformProfile, ...]:
    if value == "all":
        return tuple(PLATFORM_PROFILES[key] for key in PLATFORM_ORDER)
    if value not in PLATFORM_PROFILES:
        supported = ", ".join((*PLATFORM_ORDER, "all"))
        raise ValueError(f"unsupported platform: {value}; choose {supported}")
    return (PLATFORM_PROFILES[value],)
