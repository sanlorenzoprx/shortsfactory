from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from content_factory.config import Config


@dataclass(frozen=True)
class MusicResult:
    status: str
    source: str
    output_path: Path | None
    volume: float
    mixed_output_path: Path | None
    warnings: list[str]


class MusicAgent:
    """Creates or validates a local music bed and mixes it under existing audio."""

    def __init__(self, config: Config):
        self.config = config

    def create_mix(
        self, *, video_path: Path, job_dir: Path, duration_seconds: float
    ) -> MusicResult:
        volume = self._validated_volume()
        warnings: list[str] = []
        status = "success"

        try:
            source, music_path = self._prepare_music(
                job_dir=job_dir, duration_seconds=duration_seconds
            )
        except Exception as exc:
            if self.config.music_strict:
                raise
            details = " ".join(str(exc).split()) or type(exc).__name__
            warnings.append(
                f"Music source failed ({details[:240]}); generated local fallback music"
            )
            source = "generated"
            status = "fallback"
            music_path = job_dir / "background_music.wav"
            self._generate_music(music_path, duration_seconds)

        mixed_path = job_dir / "short_with_voice_and_music.mp4"
        try:
            self._mux(video_path, music_path, mixed_path, volume)
        except Exception as exc:
            if self.config.music_strict:
                raise
            details = " ".join(str(exc).split()) or type(exc).__name__
            warnings.append(f"music_mix_failed: {details[:300]}")
            return MusicResult(
                status="failed",
                source=source,
                output_path=music_path,
                volume=volume,
                mixed_output_path=None,
                warnings=warnings,
            )

        return MusicResult(
            status=status,
            source=source,
            output_path=music_path,
            volume=volume,
            mixed_output_path=mixed_path,
            warnings=warnings,
        )

    def _prepare_music(self, *, job_dir: Path, duration_seconds: float) -> tuple[str, Path]:
        source = self.config.music_source.strip().lower() or "generated"
        if source == "generated":
            output_path = job_dir / "background_music.wav"
            self._generate_music(output_path, duration_seconds)
            return source, output_path
        if source != "local":
            raise ValueError(f"Unsupported music source: {self.config.music_source}")

        configured_path = self.config.music_path.strip()
        if not configured_path:
            raise FileNotFoundError("MUSIC_PATH is required when MUSIC_SOURCE=local")
        source_path = Path(configured_path).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError(f"Music file does not exist: {source_path}")
        self._require_audio_stream(source_path)
        suffix = source_path.suffix.lower() or ".audio"
        output_path = job_dir / f"background_music{suffix}"
        if source_path.resolve() != output_path.resolve():
            shutil.copy2(source_path, output_path)
        return source, output_path

    def _validated_volume(self) -> float:
        volume = float(self.config.music_volume)
        if not 0.0 <= volume <= 1.0:
            raise ValueError("MUSIC_VOLUME must be between 0.0 and 1.0")
        return volume

    @staticmethod
    def _generate_music(output_path: Path, duration_seconds: float) -> None:
        """Generate a deterministic, royalty-safe ambient chord progression."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 22_050
        duration = max(1.0, float(duration_seconds))
        frame_count = int(sample_rate * duration)
        chords = (
            (220.00, 277.18, 329.63),
            (196.00, 246.94, 293.66),
            (174.61, 220.00, 261.63),
            (196.00, 246.94, 329.63),
        )
        amplitude = 5_000
        frames = bytearray()
        for index in range(frame_count):
            time_seconds = index / sample_rate
            chord = chords[int(time_seconds // 4) % len(chords)]
            fade = min(1.0, time_seconds, max(0.0, duration - time_seconds))
            pulse = 0.82 + 0.18 * math.sin(2.0 * math.pi * 0.25 * time_seconds)
            value = sum(
                math.sin(2.0 * math.pi * frequency * time_seconds)
                for frequency in chord
            ) / len(chord)
            frames.extend(struct.pack("<h", int(amplitude * fade * pulse * value)))

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(frames)
        if output_path.stat().st_size <= 44:
            raise RuntimeError("Generated background music is empty")

    @staticmethod
    def _ffmpeg_executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise RuntimeError(f"{name} is required for background music mixing")
        return str(Path(executable).resolve())

    def _require_audio_stream(self, path: Path) -> None:
        completed = subprocess.run(
            [
                self._ffmpeg_executable("ffprobe"),
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise ValueError(f"Music file has no readable audio stream: {path}")

    def _has_audio_stream(self, path: Path) -> bool:
        try:
            self._require_audio_stream(path)
            return True
        except (RuntimeError, ValueError):
            return False

    @staticmethod
    def _audio_filter(has_existing_audio: bool, volume: float) -> str:
        music = f"[1:a:0]volume={volume:.6f}[music]"
        if has_existing_audio:
            return (
                f"{music};[0:a:0][music]"
                "amix=inputs=2:duration=first:dropout_transition=2:normalize=0,apad[a]"
            )
        return f"{music};[music]apad[a]"

    def _mux(
        self, video_path: Path, music_path: Path, output_path: Path, volume: float
    ) -> None:
        command = [
            self._ffmpeg_executable("ffmpeg"),
            "-y",
            "-i",
            str(video_path),
            "-stream_loop",
            "-1",
            "-i",
            str(music_path),
            "-filter_complex",
            self._audio_filter(self._has_audio_stream(video_path), volume),
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(
            command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if completed.returncode == 0:
            return

        reencode = command.copy()
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
            raise RuntimeError(f"ffmpeg could not mix background music: {details}")
