from __future__ import annotations

from pathlib import Path
from typing import List

from content_factory.schemas import ShortScript
from content_factory.templates import TemplateRenderError, TemplateStore, render_template


def _fmt_time(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


class CaptionAgent:
    def __init__(self, template_root: str | Path = "templates"):
        self.template_root = template_root
        self.last_template_usage: dict[str, str] | None = None
        self.last_template_warning: str | None = None

    def generate_captions(self, script: ShortScript, output_path: Path, locale: str = "en-US") -> Path:
        lines: List[str] = [script.hook, *script.body_lines, script.verdict_reveal, script.cta]
        self.last_template_usage = None
        self.last_template_warning = None
        template = TemplateStore(self.template_root).get("caption.default")
        if template is not None:
            try:
                rendered = render_template(template, {"caption": script.as_text(), "hook": script.hook, "top_reason": script.body_lines[-1] if script.body_lines else "", "cta": script.cta, "locale": locale})
                rendered_text = "\n".join(rendered) if isinstance(rendered, list) else rendered
                candidate = [line.strip() for line in rendered_text.splitlines() if line.strip()]
                if not candidate:
                    raise TemplateRenderError("caption template rendered no text")
                lines = candidate
                self.last_template_usage = {"template_id": "caption.default", "template_version_hash": str(template["template_version_hash"]), "source": "local_template"}
            except (TemplateRenderError, KeyError, TypeError, ValueError) as exc:
                self.last_template_warning = f"caption.default template invalid; deterministic fallback used: {exc}"
        else:
            self.last_template_warning = "caption.default template missing or unreadable; deterministic fallback used"
        slot = 30 / max(len(lines), 1)
        chunks = []
        for i, line in enumerate(lines, start=1):
            start = (i - 1) * slot
            end = min(i * slot, 30)
            chunks.append(f"{i}\n{_fmt_time(start)} --> {_fmt_time(end)}\n{line}\n")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(chunks), encoding="utf-8")
        return output_path
