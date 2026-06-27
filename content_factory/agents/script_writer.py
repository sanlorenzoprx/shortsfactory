from __future__ import annotations

from content_factory.schemas import LitVerdict, ShortScript


class ScriptWriter:
    """Deterministic script writer for MVP.

    No LLM call. This keeps tests stable and prevents prompt drift.
    """

    def generate_script(self, verdict: LitVerdict, locale: str = "en-US") -> ShortScript:
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
