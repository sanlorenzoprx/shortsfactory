from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional at runtime. The MVP must still run without it.
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Runtime settings for the boring MVP pipeline.

    No paid APIs are required in mock mode. The goal is to create real local files
    first, then add external integrations after the tests are green.
    """

    mode: str = field(default_factory=lambda: os.getenv("CONTENT_FACTORY_MODE", "mock"))
    lit_api_url: str = field(
        default_factory=lambda: os.getenv("LIT_API_URL", "http://localhost:8787/api/verdict")
    )
    lit_api_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("LIT_API_TIMEOUT_SECONDS", "20"))
    )
    lit_api_key: str = field(default_factory=lambda: os.getenv("LIT_API_KEY", ""), repr=False)
    lit_app_url: str = field(
        default_factory=lambda: os.getenv("LIT_APP_URL", "http://127.0.0.1:5173")
    )
    playwright_headless: bool = field(
        default_factory=lambda: _env_bool("PLAYWRIGHT_HEADLESS", True)
    )
    playwright_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))
    )
    playwright_recording_enabled: bool = field(
        default_factory=lambda: _env_bool("PLAYWRIGHT_RECORDING_ENABLED", False)
    )
    playwright_viewport_width: int = field(
        default_factory=lambda: int(os.getenv("PLAYWRIGHT_VIEWPORT_WIDTH", "1080"))
    )
    playwright_viewport_height: int = field(
        default_factory=lambda: int(os.getenv("PLAYWRIGHT_VIEWPORT_HEIGHT", "1920"))
    )
    tts_enabled: bool = field(default_factory=lambda: _env_bool("TTS_ENABLED", False))
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "auto"))
    tts_voice: str = field(default_factory=lambda: os.getenv("TTS_VOICE", ""))
    tts_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("TTS_TIMEOUT_SECONDS", "30"))
    )
    tts_strict: bool = field(default_factory=lambda: _env_bool("TTS_STRICT", False))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "output")))
    video_width: int = 1080
    video_height: int = 1920
    video_seconds: int = 30
    fps: int = 30

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
