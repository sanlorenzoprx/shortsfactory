from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from content_factory.schemas import LitVerdict, ShortScript
from content_factory.utils.files import write_json


PLATFORMS = ("youtube_shorts", "tiktok", "instagram_reels")


@dataclass(frozen=True)
class PublisherResult:
    status: str
    platforms: list[str]
    plan_path: Path
    warnings: list[str]


class PublisherAgent:
    """Builds local publish manifests. It never uploads or calls a platform API."""

    def create_dry_run_packages(
        self,
        *,
        job_id: str,
        locale: str,
        script: ShortScript,
        verdict: LitVerdict,
        video_path: Path,
        thumbnail_path: Path,
        captions_path: Path,
        job_dir: Path,
    ) -> PublisherResult:
        self._require_file(video_path, "final video")
        self._require_file(thumbnail_path, "thumbnail")
        self._require_file(captions_path, "captions")
        publish_dir = job_dir / "publish"
        publish_dir.mkdir(parents=True, exist_ok=True)

        title = verdict.verdict_headline.rstrip(".!?")
        description = " ".join(
            [script.hook, verdict.top_reason, script.cta]
        ).strip()
        plan_platforms: dict[str, str] = {}
        for platform in PLATFORMS:
            platform_dir = publish_dir / platform
            platform_dir.mkdir(parents=True, exist_ok=True)
            platform_captions = platform_dir / "captions.srt"
            shutil.copy2(captions_path, platform_captions)
            hashtags = self._hashtags(platform, locale)
            metadata_path = platform_dir / "metadata.json"
            metadata = {
                "status": "dry_run_ready",
                "live_publish_enabled": False,
                "platform": platform,
                "source_job_id": job_id,
                "locale": locale,
                "title": title,
                "description": description,
                "caption": f"{script.cta} {' '.join(hashtags)}",
                "hashtags": hashtags,
                "video": self._relative(video_path, platform_dir),
                "thumbnail": self._relative(thumbnail_path, platform_dir),
                "captions": platform_captions.name,
            }
            write_json(metadata_path, metadata)
            plan_platforms[platform] = self._relative(metadata_path, publish_dir)

        plan_path = publish_dir / "publisher_plan.json"
        write_json(
            plan_path,
            {
                "status": "dry_run_ready",
                "live_publish_enabled": False,
                "requires_human_approval": True,
                "source_job_id": job_id,
                "locale": locale,
                "video": self._relative(video_path, publish_dir),
                "thumbnail": self._relative(thumbnail_path, publish_dir),
                "platforms": plan_platforms,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return PublisherResult(
            status="dry_run_ready",
            platforms=list(PLATFORMS),
            plan_path=plan_path,
            warnings=[],
        )

    @staticmethod
    def refuse_live_publish() -> None:
        raise RuntimeError(
            "Live publishing is not implemented in Phase 2G. "
            "This phase only creates dry-run publish packages."
        )

    @staticmethod
    def _hashtags(platform: str, locale: str) -> list[str]:
        if locale == "es-PR":
            common = ["#IdeasDeNegocio", "#Emprendimiento", "#Validación"]
        else:
            common = ["#BusinessIdeas", "#Startup", "#Validation"]
        platform_tag = {
            "youtube_shorts": "#Shorts",
            "tiktok": "#TikTok",
            "instagram_reels": "#Reels",
        }[platform]
        return [*common, platform_tag]

    @staticmethod
    def _relative(path: Path, start: Path) -> str:
        return os.path.relpath(path.resolve(), start.resolve()).replace("\\", "/")

    @staticmethod
    def _require_file(path: Path, label: str) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Publisher {label} is missing or empty: {path}")
