from __future__ import annotations

from pathlib import Path

from content_factory.schemas import LitVerdict, ShortScript
from content_factory.templates import TemplateRenderError, TemplateStore, render_template


class ScriptWriter:
    """Deterministic script writer for MVP.

    No LLM call. This keeps tests stable and prevents prompt drift.
    """

    def __init__(self, template_root: str | Path = "templates"):
        self.template_root = template_root
        self.last_template_usage: dict[str, str] | None = None
        self.last_template_warning: str | None = None

    def _legacy_script(self, verdict: LitVerdict, locale: str) -> ShortScript:
        idea = verdict.idea.name
        headline = verdict.verdict_headline.rstrip(".!?")
        if locale == "es-PR":
            return ShortScript(
                hook=f"Probé esta idea con Ghost Town: {idea}.",
                body_lines=[
                    f"Puntuación: {verdict.lit_score}/100.",
                    f"Riesgo principal: {verdict.risk_level}.",
                    verdict.top_reason,
                ],
                verdict_reveal=f"Veredicto: {headline}.",
                cta="Prueba tu idea antes de construir.",
            )
        return ShortScript(
            hook=f"I ran this business idea through the Ghost Town Test: {idea}.",
            body_lines=[
                f"Score: {verdict.lit_score}/100.",
                f"Main risk: {verdict.risk_level}.",
                verdict.top_reason,
            ],
            verdict_reveal=f"Verdict: {headline}.",
            cta="Do not build blind. Test your idea first.",
        )

    def generate_script(self, verdict: LitVerdict, locale: str = "en-US") -> ShortScript:
        self.last_template_usage = None
        self.last_template_warning = None
        legacy = self._legacy_script(verdict, locale)
        if locale != "en-US":
            return legacy
        template = TemplateStore(self.template_root).get("script.default")
        if template is None:
            self.last_template_warning = "script.default template missing or unreadable; deterministic fallback used"
            return legacy
        try:
            rendered = render_template(
                template,
                {
                    "idea": verdict.idea.name,
                    "hook": legacy.hook,
                    "verdict_headline": verdict.verdict_headline.rstrip(".!?"),
                    "lit_score": verdict.lit_score,
                    "risk_level": verdict.risk_level,
                    "top_reason": verdict.top_reason,
                    "next_step": verdict.next_step,
                    "source": verdict.source,
                    "locale": locale,
                    "cta": legacy.cta,
                },
            )
            lines = rendered if isinstance(rendered, list) else rendered.splitlines()
            lines = [line.strip() for line in lines if line.strip()]
            if len(lines) < 3:
                raise TemplateRenderError("script template must render at least three lines")
            script = ShortScript(
                hook=lines[0],
                body_lines=lines[1:-2],
                verdict_reveal=lines[-2],
                cta=lines[-1],
            )
            self.last_template_usage = {
                "template_id": str(template["template_id"]),
                "template_version_hash": str(template["template_version_hash"]),
                "source": "local_template",
            }
            return script
        except (TemplateRenderError, KeyError, TypeError, ValueError) as exc:
            self.last_template_warning = f"script.default template invalid; deterministic fallback used: {exc}"
            return legacy
