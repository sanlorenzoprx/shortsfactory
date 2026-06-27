from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from content_factory.agents.music_agent import MusicAgent
from content_factory.config import Config
from orchestrator import ContentFactoryOrchestrator, parse_args


def _ffmpeg(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"{name} is required for the music integration test")
    return str(Path(executable).resolve())


def _video_with_voice_tone(path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg("ffmpeg"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=108x192:r=10:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=44100:duration=1",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return path


def _fast_orchestrator(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> ContentFactoryOrchestrator:
    orchestrator = ContentFactoryOrchestrator(config)
    monkeypatch.setattr(
        orchestrator.video,
        "create_short",
        lambda _script, _verdict, job_dir: _video_with_voice_tone(
            job_dir / "short.mp4"
        ),
    )
    return orchestrator


def _decode_pcm(path: Path) -> array:
    decoded = subprocess.run(
        [
            _ffmpeg("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            "22050",
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    samples = array("h")
    samples.frombytes(decoded.stdout)
    return samples


def _correlation(first: array, second: array) -> float:
    count = min(len(first), len(second))
    first = first[:count]
    second = second[:count]
    first_mean = sum(first) / count
    second_mean = sum(second) / count
    numerator = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first, second)
    )
    first_energy = sum((value - first_mean) ** 2 for value in first)
    second_energy = sum((value - second_mean) ** 2 for value in second)
    return numerator / math.sqrt(first_energy * second_energy)


def test_music_disabled_by_default_and_cli_flag_is_explicit(monkeypatch):
    monkeypatch.delenv("MUSIC_ENABLED", raising=False)
    assert Config().music_enabled is False

    monkeypatch.setattr(sys, "argv", ["orchestrator.py"])
    assert parse_args().music is False
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--music"])
    assert parse_args().music is True


def test_generated_music_creates_audio_mix_and_receipt(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        video_seconds=1,
        music_enabled=True,
        music_source="generated",
        music_volume=0.12,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    music_path = Path(receipt["outputs"]["background_music_audio"])
    mixed_path = Path(receipt["outputs"]["short_with_voice_and_music_mp4"])
    assert music_path.name == "background_music.wav"
    assert music_path.stat().st_size > 44
    assert mixed_path.name == "short_with_voice_and_music.mp4"
    assert mixed_path.stat().st_size > 0
    assert receipt["music"] == {
        "status": "success",
        "source": "generated",
        "output": "background_music.wav",
        "volume": 0.12,
        "mixed_output": "short_with_voice_and_music.mp4",
        "warnings": [],
    }

    probe = subprocess.run(
        [
            _ffmpeg("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,duration",
            "-of",
            "json",
            str(mixed_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    streams = json.loads(probe.stdout.decode("utf-8"))["streams"]
    assert streams and streams[0]["codec_name"] == "aac"
    original_path = Path(receipt["outputs"]["short_mp4"])
    assert _correlation(_decode_pcm(original_path), _decode_pcm(mixed_path)) > 0.8


def test_missing_local_music_falls_back_safely(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        video_seconds=1,
        music_enabled=True,
        music_source="local",
        music_path=str(tmp_path / "missing.mp3"),
        music_strict=False,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["music"]["status"] == "fallback"
    assert receipt["music"]["source"] == "generated"
    assert "Music file does not exist" in receipt["music"]["warnings"][0]
    assert Path(receipt["outputs"]["background_music_audio"]).stat().st_size > 44
    assert Path(receipt["outputs"]["short_with_voice_and_music_mp4"]).exists()


def test_mix_filter_keeps_voiceover_and_lowers_music():
    audio_filter = MusicAgent._audio_filter(has_existing_audio=True, volume=0.12)

    assert "[0:a:0]" in audio_filter
    assert "volume=0.120000" in audio_filter
    assert "amix=inputs=2" in audio_filter
    assert "normalize=0" in audio_filter
