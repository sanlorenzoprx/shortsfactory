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
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "output")))
    video_width: int = 1080
    video_height: int = 1920
    video_seconds: int = 30
    fps: int = 30

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
