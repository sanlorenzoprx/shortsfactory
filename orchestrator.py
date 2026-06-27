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
from content_factory.agents.script_writer import ScriptWriter
from content_factory.agents.thumbnail_agent import ThumbnailAgent
from content_factory.agents.video_builder import VideoBuilder
from content_factory.config import Config
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

    def run_batch(self, batch: int = 1, locale: str = "en-US") -> List[Path]:
        ideas = self.researcher.get_trending_ideas(batch)
        receipts: List[Path] = []
        for idea in ideas:
            receipt = ShortJobReceipt(locale=locale, mode=self.config.mode, idea=asdict(idea))
            job_dir = self.config.output_dir / "jobs" / receipt.job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            test_outcome = self.tester.run_test_with_details(idea, locale=locale)
            verdict = test_outcome.verdict
            script = self.writer.generate_script(verdict, locale=locale)
            script = self.localizer.adapt(script, locale)

            idea_path = write_json(job_dir / "idea.json", asdict(idea))
            verdict_path = write_json(job_dir / "verdict.json", asdict(verdict))
            script_path = write_text(job_dir / "script.txt", script.as_text())
            captions_path = self.captions.generate_captions(script, job_dir / "captions.srt")
            thumbnail_path = self.thumbnails.create_thumbnail(verdict, job_dir / "thumbnail.jpg")
            video_path = self.video.create_short(script, verdict, job_dir)

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = Config(mode=args.mode, output_dir=Path(args.output_dir))
    orchestrator = ContentFactoryOrchestrator(config)
    orchestrator.run_batch(batch=args.batch, locale=args.locale)


if __name__ == "__main__":
    main()
