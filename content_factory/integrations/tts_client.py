from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SynthesizedAudio:
    status: str
    provider: str
    output_path: Path
    warnings: list[str]


class TTSClient:
    """Small provider boundary for local-safe speech synthesis."""

    def synthesize(
        self,
        *,
        text: str,
        output_path: Path,
        provider: str,
        voice: str,
        timeout_seconds: float,
    ) -> SynthesizedAudio:
        requested = provider.strip().lower() or "auto"
        selected = self._select_provider(requested)
        if selected == "local_tone_fallback":
            self.create_tone_fallback(text=text, output_path=output_path)
            return SynthesizedAudio(
                status="fallback",
                provider=selected,
                output_path=output_path,
                warnings=["TTS provider unavailable; generated fallback audio"],
            )
        if selected == "windows_sapi":
            self._synthesize_windows_sapi(
                text=text,
                output_path=output_path,
                voice=voice,
                timeout_seconds=timeout_seconds,
            )
        elif selected == "pyttsx3":
            self._synthesize_pyttsx3(text=text, output_path=output_path, voice=voice)
        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

        self._require_audio(output_path)
        return SynthesizedAudio(
            status="success",
            provider=selected,
            output_path=output_path,
            warnings=[],
        )

    @staticmethod
    def _select_provider(provider: str) -> str:
        if provider != "auto":
            return provider
        if os.name == "nt":
            return "windows_sapi"
        return "pyttsx3"

    @staticmethod
    def _synthesize_windows_sapi(
        *, text: str, output_path: Path, voice: str, timeout_seconds: float
    ) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            raise RuntimeError("Windows PowerShell is unavailable for Windows SAPI TTS")

        input_path = output_path.with_name(".voiceover_input.txt")
        input_path.write_text(text, encoding="utf-8")
        env = os.environ.copy()
        env["SHORTS_FACTORY_TTS_INPUT"] = str(input_path.resolve())
        env["SHORTS_FACTORY_TTS_OUTPUT"] = str(output_path.resolve())
        env["SHORTS_FACTORY_TTS_VOICE"] = voice.strip()
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "try { "
            "$voice = [Environment]::GetEnvironmentVariable('SHORTS_FACTORY_TTS_VOICE'); "
            "if ($voice) { $speaker.SelectVoice($voice) }; "
            "$inputPath = [Environment]::GetEnvironmentVariable('SHORTS_FACTORY_TTS_INPUT'); "
            "$outputPath = [Environment]::GetEnvironmentVariable('SHORTS_FACTORY_TTS_OUTPUT'); "
            "$text = [IO.File]::ReadAllText($inputPath, [Text.Encoding]::UTF8); "
            "$speaker.SetOutputToWaveFile($outputPath); $speaker.Speak($text) "
            "} finally { $speaker.Dispose() }"
        )
        try:
            completed = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Windows SAPI TTS timed out after {timeout_seconds:g} seconds"
            ) from exc
        finally:
            input_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            details = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Windows SAPI TTS failed: {details or 'unknown error'}")

    @staticmethod
    def _synthesize_pyttsx3(*, text: str, output_path: Path, voice: str) -> None:
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError(
                "pyttsx3 is unavailable; install it or use a supported local provider"
            ) from exc

        engine = pyttsx3.init()
        try:
            if voice:
                matches = [
                    item.id
                    for item in engine.getProperty("voices")
                    if voice.lower() in f"{item.id} {item.name}".lower()
                ]
                if not matches:
                    raise RuntimeError(f"pyttsx3 voice not found: {voice}")
                engine.setProperty("voice", matches[0])
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
        finally:
            engine.stop()

    @staticmethod
    def create_tone_fallback(*, text: str, output_path: Path) -> None:
        """Create deterministic, audible WAV data when speech synthesis is unavailable."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 22_050
        duration = min(30.0, max(3.0, len(text.split()) * 0.18))
        frame_count = int(sample_rate * duration)
        amplitude = 7_500
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = bytearray()
            for index in range(frame_count):
                frequency = 440 if (index // (sample_rate // 3)) % 2 == 0 else 660
                envelope = min(1.0, index / 220, (frame_count - index) / 220)
                sample = int(
                    amplitude
                    * envelope
                    * math.sin(2.0 * math.pi * frequency * index / sample_rate)
                )
                frames.extend(struct.pack("<h", sample))
            wav.writeframes(frames)
        TTSClient._require_audio(output_path)

    @staticmethod
    def _require_audio(output_path: Path) -> None:
        if not output_path.exists() or output_path.stat().st_size <= 44:
            raise RuntimeError("TTS provider did not create a non-empty WAV audio file")
