from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from content_factory.config import Config
from content_factory.integrations.tts_client import SynthesizedAudio, TTSClient


@dataclass(frozen=True)
class VoiceoverResult:
    status: str
    provider: str
    output_path: Path | None
    duration_seconds: float | None
    mixed_output_path: Path | None
    warnings: list[str]


class VoiceoverAgent:
    def __init__(self, config: Config, tts_client: TTSClient | None = None):
        self.config = config
        self.tts = tts_client or TTSClient()

    def create_voiceover(
        self, *, script_path: Path, video_path: Path, job_dir: Path
    ) -> VoiceoverResult:
        text = script_path.read_text(encoding="utf-8").strip()
        if not text:
            return self._failure("TTS script is empty")

        audio_path = job_dir / "voiceover.wav"
        warnings: list[str] = []
        try:
            audio = self.tts.synthesize(
                text=text,
                output_path=audio_path,
                provider=self.config.tts_provider,
                voice=self.config.tts_voice,
                timeout_seconds=self.config.tts_timeout_seconds,
            )
        except Exception as exc:
            if self.config.tts_strict:
                raise
            details = " ".join(str(exc).split()) or type(exc).__name__
            warning = f"TTS provider failed ({details[:240]}); generated fallback audio"
            self.tts.create_tone_fallback(text=text, output_path=audio_path)
            audio = SynthesizedAudio(
                status="fallback",
                provider="local_tone_fallback",
                output_path=audio_path,
                warnings=[warning],
            )

        warnings.extend(audio.warnings)
        duration = self._probe_duration(audio.output_path)
        video_duration = self._probe_duration(video_path)
        if duration is not None and video_duration is not None and duration > video_duration + 0.05:
            warnings.append("Voiceover exceeded video duration and was trimmed during muxing")

        mixed_path = job_dir / "short_with_voice.mp4"
        try:
            self._mux(video_path, audio.output_path, mixed_path)
        except Exception as exc:
            if self.config.tts_strict:
                raise
            details = " ".join(str(exc).split()) or type(exc).__name__
            warnings.append(f"voiceover_mux_failed: {details[:300]}")
            return VoiceoverResult(
                status="failed",
                provider=audio.provider,
                output_path=audio.output_path,
                duration_seconds=duration,
                mixed_output_path=None,
                warnings=warnings,
            )

        return VoiceoverResult(
            status=audio.status,
            provider=audio.provider,
            output_path=audio.output_path,
            duration_seconds=duration,
            mixed_output_path=mixed_path,
            warnings=warnings,
        )

    def _failure(self, warning: str) -> VoiceoverResult:
        if self.config.tts_strict:
            raise RuntimeError(warning)
        return VoiceoverResult(
            status="failed",
            provider=self.config.tts_provider,
            output_path=None,
            duration_seconds=None,
            mixed_output_path=None,
            warnings=[warning],
        )

    @staticmethod
    def _ffmpeg_executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise RuntimeError(f"{name} is required for voiceover audio")
        return str(Path(executable).resolve())

    def _probe_duration(self, path: Path) -> float | None:
        try:
            completed = subprocess.run(
                [
                    self._ffmpeg_executable("ffprobe"),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            value = json.loads(completed.stdout.decode("utf-8"))["format"]["duration"]
            return round(float(value), 3)
        except Exception:
            return None

    def _mux(self, video_path: Path, audio_path: Path, output_path: Path) -> None:
        base = [
            self._ffmpeg_executable("ffmpeg"),
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-af",
            "apad",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(
            base, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if completed.returncode == 0:
            return

        reencode = base.copy()
        codec_index = reencode.index("copy")
        reencode[codec_index : codec_index + 1] = [
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
        ]
        retry = subprocess.run(
            reencode, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if retry.returncode != 0:
            details = retry.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg could not mux voiceover: {details}")
