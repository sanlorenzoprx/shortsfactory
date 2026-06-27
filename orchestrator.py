from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import List

from content_factory.agents.app_tester import AppTester
from content_factory.agents.caption_agent import CaptionAgent
from content_factory.agents.idea_researcher import IdeaResearcher
from content_factory.agents.localization_agent import LocalizationAgent
from content_factory.agents.music_agent import MusicAgent
from content_factory.agents.script_writer import ScriptWriter
from content_factory.agents.thumbnail_agent import ThumbnailAgent
from content_factory.agents.video_builder import VideoBuilder
from content_factory.agents.voiceover_agent import VoiceoverAgent
from content_factory.config import Config
from content_factory.integrations.playwright_recorder import record_lit_app_flow
from content_factory.schemas import ShortJobReceipt
from content_factory.utils.files import write_json, write_text


class ContentFactoryOrchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.config.ensure_dirs()
        self.researcher = IdeaResearcher()
        self.tester = AppTester(config)
        self.writer = ScriptWriter()
        self.localizer = LocalizationAgent()
        self.captions = CaptionAgent()
        self.thumbnails = ThumbnailAgent()
        self.video = VideoBuilder(config)
        self.voiceover = VoiceoverAgent(config)
        self.music = MusicAgent(config)

    def run_batch(self, batch: int = 1, locale: str = "en-US") -> List[Path]:
        ideas = self.researcher.get_trending_ideas(batch)
        receipts: List[Path] = []
        for idea in ideas:
            receipt = ShortJobReceipt(locale=locale, mode=self.config.mode, idea=asdict(idea))
            job_dir = self.config.output_dir / "jobs" / receipt.job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            test_outcome = self.tester.run_test_with_details(idea, locale=locale)
            localization = self.localizer.resolve(locale)
            verdict, localization_warnings = self.localizer.localize_verdict(
                test_outcome.verdict, localization
            )
            localization_warnings = [
                *localization.warnings,
                *localization_warnings,
            ]
            script = self.writer.generate_script(
                verdict, locale=localization.resolved_locale
            )
            receipt.idea = asdict(verdict.idea)
            receipt.localization = {
                "status": localization.status,
                "requested_locale": localization.requested_locale,
                "resolved_locale": localization.resolved_locale,
                "fallback_locale": localization.fallback_locale,
                "localized_outputs": [
                    "script.txt",
                    "captions.srt",
                    "thumbnail.jpg",
                    "short.mp4",
                ],
                "warnings": localization_warnings,
            }
            receipt.warnings.extend(localization_warnings)

            idea_path = write_json(job_dir / "idea.json", asdict(verdict.idea))
            verdict_path = write_json(job_dir / "verdict.json", asdict(verdict))
            script_path = write_text(job_dir / "script.txt", script.as_text())
            captions_path = self.captions.generate_captions(script, job_dir / "captions.srt")
            thumbnail_path = self.thumbnails.create_thumbnail(
                verdict,
                job_dir / "thumbnail.jpg",
                locale=localization.resolved_locale,
            )
            video_path = self.video.create_short(
                script,
                verdict,
                job_dir,
                locale=localization.resolved_locale,
            )

            outputs = {
                "idea_json": str(idea_path),
                "verdict_json": str(verdict_path),
                "script_txt": str(script_path),
                "captions_srt": str(captions_path),
                "thumbnail_jpg": str(thumbnail_path),
                "short_mp4": str(video_path),
            }
            if test_outcome.raw_response is not None:
                api_response_path = write_json(
                    job_dir / "lit_api_response.json", test_outcome.raw_response
                )
                outputs["lit_api_response_json"] = str(api_response_path)
            if test_outcome.warning:
                receipt.warnings.append(test_outcome.warning)

            final_audio_video_path = video_path
            if self.config.tts_enabled:
                voiceover = self.voiceover.create_voiceover(
                    script_path=script_path,
                    video_path=video_path,
                    job_dir=job_dir,
                )
                receipt.voiceover = {
                    "status": voiceover.status,
                    "provider": voiceover.provider,
                    "script_source": script_path.name,
                    "output": voiceover.output_path.name if voiceover.output_path else None,
                    "duration_seconds": voiceover.duration_seconds,
                    "mixed_output": (
                        voiceover.mixed_output_path.name
                        if voiceover.mixed_output_path
                        else None
                    ),
                    "warnings": voiceover.warnings,
                }
                receipt.warnings.extend(voiceover.warnings)
                if voiceover.output_path is not None:
                    outputs["voiceover_audio"] = str(voiceover.output_path)
                if voiceover.mixed_output_path is not None:
                    outputs["short_with_voice_mp4"] = str(voiceover.mixed_output_path)
                    final_audio_video_path = voiceover.mixed_output_path

            if self.config.music_enabled:
                music = self.music.create_mix(
                    video_path=final_audio_video_path,
                    job_dir=job_dir,
                    duration_seconds=self.config.video_seconds,
                )
                music_warnings = list(music.warnings)
                if self.config.tts_enabled and final_audio_video_path == video_path:
                    music_warnings.append(
                        "Voiceover mix was unavailable; mixed music with short.mp4"
                    )
                receipt.music = {
                    "status": music.status,
                    "source": music.source,
                    "output": music.output_path.name if music.output_path else None,
                    "volume": music.volume,
                    "mixed_output": (
                        music.mixed_output_path.name if music.mixed_output_path else None
                    ),
                    "warnings": music_warnings,
                }
                receipt.warnings.extend(music_warnings)
                if music.output_path is not None:
                    outputs["background_music_audio"] = str(music.output_path)
                if music.mixed_output_path is not None:
                    outputs["short_with_voice_and_music_mp4"] = str(
                        music.mixed_output_path
                    )

            if self.config.playwright_recording_enabled:
                try:
                    recording = record_lit_app_flow(
                        app_url=self.config.lit_app_url,
                        idea=verdict.idea.name,
                        verdict=asdict(verdict),
                        job_dir=job_dir,
                        locale=locale,
                        headless=self.config.playwright_headless,
                        timeout_ms=self.config.playwright_timeout_ms,
                        viewport_width=self.config.playwright_viewport_width,
                        viewport_height=self.config.playwright_viewport_height,
                    )
                    receipt.recording = recording.metadata
                    receipt.warnings.extend(recording.warnings)
                    if recording.success:
                        if recording.raw_video_path is not None:
                            outputs["app_recording_raw_webm"] = str(recording.raw_video_path)
                        if recording.normalized_video_path is not None:
                            outputs["app_recording_mp4"] = str(recording.normalized_video_path)
                        if recording.screenshot_path is not None:
                            outputs["app_recording_final_png"] = str(recording.screenshot_path)
                except Exception as exc:
                    details = " ".join(str(exc).split()) or type(exc).__name__
                    receipt.recording = {
                        "enabled": True,
                        "source": "playwright",
                        "app_url": self.config.lit_app_url,
                        "status": "failed",
                        "error_code": "recording_error",
                    }
                    receipt.warnings.append(f"app_recording_failed: {details[:300]}")

            receipt.verdict = asdict(verdict)
            receipt.outputs = outputs
            receipt_path = write_json(job_dir / "receipt.json", receipt.to_json_dict())
            receipts.append(receipt_path)
            print(f"Created {video_path}")
            print(f"Receipt {receipt_path}")
        return receipts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boring MVP Shorts Factory")
    parser.add_argument("--batch", type=int, default=1, help="Number of mock shorts to create")
    parser.add_argument("--locale", default="en-US", help="Locale tag, e.g. en-US")
    parser.add_argument("--mode", choices=["mock", "api"], default="mock", help="mock is offline-safe")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument(
        "--record-app",
        action="store_true",
        help="Record the controlled LIT demo flow for this run",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Generate a local voiceover and mux it into short_with_voice.mp4",
    )
    parser.add_argument(
        "--music",
        action="store_true",
        help="Generate or load background music and mix it under existing audio",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = Config(
        mode=args.mode,
        output_dir=Path(args.output_dir),
        playwright_recording_enabled=args.record_app,
        tts_enabled=args.tts,
        music_enabled=args.music,
    )
    orchestrator = ContentFactoryOrchestrator(config)
    orchestrator.run_batch(batch=args.batch, locale=args.locale)


if __name__ == "__main__":
    main()
