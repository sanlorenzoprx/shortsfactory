from __future__ import annotations

from pathlib import Path
from typing import List

from content_factory.schemas import ShortScript


def _fmt_time(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


class CaptionAgent:
    def generate_captions(self, script: ShortScript, output_path: Path) -> Path:
        lines: List[str] = [script.hook, *script.body_lines, script.verdict_reveal, script.cta]
        slot = 30 / max(len(lines), 1)
        chunks = []
        for i, line in enumerate(lines, start=1):
            start = (i - 1) * slot
            end = min(i * slot, 30)
            chunks.append(f"{i}\n{_fmt_time(start)} --> {_fmt_time(end)}\n{line}\n")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(chunks), encoding="utf-8")
        return output_path
