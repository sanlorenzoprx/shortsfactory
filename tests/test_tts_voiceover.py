from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from content_factory.config import Config
from orchestrator import ContentFactoryOrchestrator, parse_args


def _ffmpeg(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"{name} is required for the voiceover integration test")
    return str(Path(executable).resolve())


def _fast_video(path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg("ffmpeg"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=108x192:r=10:d=1",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
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
        lambda _script, _verdict, job_dir: _fast_video(job_dir / "short.mp4"),
    )
    return orchestrator


def test_tts_disabled_by_default_and_cli_flag_is_explicit(monkeypatch):
    monkeypatch.delenv("TTS_ENABLED", raising=False)
    assert Config().tts_enabled is False

    monkeypatch.setattr(sys, "argv", ["orchestrator.py"])
    assert parse_args().tts is False
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--tts"])
    assert parse_args().tts is True


def test_tts_creates_audio_mixed_video_stream_and_receipt(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        tts_enabled=True,
        tts_provider="local_tone_fallback",
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    audio_path = Path(receipt["outputs"]["voiceover_audio"])
    mixed_path = Path(receipt["outputs"]["short_with_voice_mp4"])
    assert audio_path.name == "voiceover.wav"
    assert audio_path.stat().st_size > 44
    assert mixed_path.name == "short_with_voice.mp4"
    assert mixed_path.stat().st_size > 0
    assert receipt["voiceover"]["status"] == "fallback"
    assert receipt["voiceover"]["provider"] == "local_tone_fallback"
    assert receipt["voiceover"]["script_source"] == "script.txt"
    assert receipt["voiceover"]["output"] == "voiceover.wav"
    assert receipt["voiceover"]["mixed_output"] == "short_with_voice.mp4"
    assert receipt["voiceover"]["duration_seconds"] > 0

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
    assert streams
    assert streams[0]["codec_name"] == "aac"


def test_provider_failure_falls_back_without_killing_job(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        tts_enabled=True,
        tts_provider="unavailable_provider",
        tts_strict=False,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["voiceover"]["status"] == "fallback"
    assert receipt["voiceover"]["provider"] == "local_tone_fallback"
    assert "Unsupported TTS provider" in receipt["voiceover"]["warnings"][0]
    assert Path(receipt["outputs"]["short_mp4"]).exists()
    assert Path(receipt["outputs"]["short_with_voice_mp4"]).exists()
