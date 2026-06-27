from __future__ import annotations

from content_factory.schemas import ShortScript


class LocalizationAgent:
    """Locale adapter placeholder that does not call LLMs in MVP.

    It preserves the script and records locale. Real cultural adaptation is Phase 2.
    """

    def adapt(self, script: ShortScript, locale: str) -> ShortScript:
        if locale == "en-US":
            return script
        return ShortScript(
            hook=f"[{locale}] {script.hook}",
            body_lines=script.body_lines,
            verdict_reveal=script.verdict_reveal,
            cta=script.cta,
        )
