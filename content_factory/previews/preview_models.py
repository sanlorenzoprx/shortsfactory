from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


PLATFORM_ORDER = ("youtube_shorts", "tiktok", "instagram_reels")
PLATFORM_NAMES = {
    "youtube_shorts": "YouTube Shorts",
    "tiktok": "TikTok",
    "instagram_reels": "Instagram Reels",
}
SAFETY_FLAGS = {
    "manual_upload_only": True,
    "publishing_status": "not_published",
    "live_publishing_enabled": False,
    "api_upload_attempted": False,
    "requires_human_upload": True,
}


@dataclass(frozen=True)
class PlatformPreview:
    platform: str
    display_name: str
    video_path: Path
    thumbnail_path: Path | None
    title: str
    caption: str
    description: str
    hashtags: tuple[str, ...]
    checklist: str
    metadata: dict[str, Any]
    warnings: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class PreviewResult:
    job_id: str
    preview_dir: Path
    manifest: dict[str, Any]
