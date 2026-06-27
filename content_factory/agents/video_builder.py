from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from textwrap import wrap
from typing import List

from PIL import Image, ImageDraw, ImageFont

from content_factory.config import Config
from content_factory.schemas import LitVerdict, ShortScript


class VideoBuilder:
    """Creates a real vertical MP4 without relying on drawtext escaping.

    MVP strategy: render text scenes as PNGs with Pillow, then stitch them with
    ffmpeg. This is boring, safe, and avoids fragile ffmpeg text escaping.
    """

    def __init__(self, config: Config):
        self.config = config

    @staticmethod
    def _ffmpeg_executable() -> str:
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise RuntimeError("ffmpeg is required to build short.mp4 but was not found on PATH")

        # WinGet can expose shared ffmpeg through a symlink. Running that link
        # makes Windows search beside the link instead of beside ffmpeg's DLLs,
        # so resolve it to the real executable before launch.
        return str(Path(executable).resolve())

    def create_short(self, script: ShortScript, verdict: LitVerdict, job_dir: Path) -> Path:
        scenes_dir = job_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        scene_paths = self._render_scenes(script, verdict, scenes_dir)
        concat_path = job_dir / "concat.txt"
        duration = self.config.video_seconds / len(scene_paths)
        concat_lines: List[str] = []
        for path in scene_paths:
            concat_lines.append(f"file '{path.resolve().as_posix()}'")
            concat_lines.append(f"duration {duration:.3f}")
        concat_lines.append(f"file '{scene_paths[-1].resolve().as_posix()}'")
        concat_path.write_text("\n".join(concat_lines), encoding="utf-8")

        output_path = job_dir / "short.mp4"
        cmd = [
            self._ffmpeg_executable(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf",
            f"fps={self.config.fps},format=yuv420p",
            "-shortest",
            "-t",
            str(self.config.video_seconds),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            details = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg could not create {output_path}: {details}") from exc
        return output_path

    def _render_scenes(self, script: ShortScript, verdict: LitVerdict, scenes_dir: Path) -> List[Path]:
        scene_specs = [
            ("01_hook.png", "I TESTED THIS IDEA", script.hook),
            ("02_score.png", f"SCORE: {verdict.lit_score}/100", f"Risk level: {verdict.risk_level}"),
            ("03_reason.png", "WHY IT MATTERS", verdict.top_reason),
            ("04_verdict.png", "VERDICT", verdict.verdict_headline),
            ("05_cta.png", "DO NOT BUILD BLIND", script.cta),
        ]
        paths = []
        for filename, title, body in scene_specs:
            path = scenes_dir / filename
            self._render_scene(path, title, body)
            paths.append(path)
        return paths

    def _render_scene(self, output_path: Path, title: str, body: str) -> None:
        img = Image.new("RGB", (self.config.video_width, self.config.video_height), color=(2, 6, 23))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 74)
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
            footer_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
        except Exception:
            title_font = body_font = footer_font = ImageFont.load_default()

        draw.rounded_rectangle((60, 90, 1020, 250), radius=30, fill=(15, 23, 42), outline=(34, 197, 94), width=4)
        draw.text((90, 125), title[:26], fill=(255, 255, 255), font=title_font)

        y = 520
        for line in wrap(body, width=24):
            draw.text((90, y), line, fill=(226, 232, 240), font=body_font)
            y += 82

        draw.text((90, 1720), "LIT Ghost Town Test", fill=(148, 163, 184), font=footer_font)
        draw.text((90, 1780), "Test the idea before you build.", fill=(148, 163, 184), font=footer_font)
        img.save(output_path)
