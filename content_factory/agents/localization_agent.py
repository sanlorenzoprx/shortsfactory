from __future__ import annotations

from dataclasses import dataclass, replace

from content_factory.locales.catalog import resolve_locale, translate_to_spanish
from content_factory.schemas import Idea, LitVerdict, ShortScript


@dataclass(frozen=True)
class LocalizationResult:
    status: str
    requested_locale: str
    resolved_locale: str
    fallback_locale: str | None
    warnings: list[str]


class LocalizationAgent:
    """Deterministic en-US/es-PR localization without external services."""

    def resolve(self, locale: str) -> LocalizationResult:
        resolved = resolve_locale(locale)
        if resolved is not None:
            return LocalizationResult(
                status="success",
                requested_locale=locale,
                resolved_locale=resolved,
                fallback_locale=None,
                warnings=[],
            )
        warning = f"Unsupported locale {locale}; fell back to en-US"
        return LocalizationResult(
            status="fallback",
            requested_locale=locale,
            resolved_locale="en-US",
            fallback_locale="en-US",
            warnings=[warning],
        )

    def localize_verdict(
        self, verdict: LitVerdict, localization: LocalizationResult
    ) -> tuple[LitVerdict, list[str]]:
        if localization.resolved_locale == "en-US":
            return verdict, []

        warnings: list[str] = []

        def translated(value: str, field: str) -> str:
            result = translate_to_spanish(value)
            if result is None:
                warnings.append(
                    f"Missing es-PR translation for {field}; used English"
                )
                return value
            return result

        idea = Idea(
            name=translated(verdict.idea.name, "idea.name"),
            description=translated(verdict.idea.description, "idea.description"),
            target_user=translated(verdict.idea.target_user, "idea.target_user"),
            market=verdict.idea.market,
        )
        return (
            replace(
                verdict,
                idea=idea,
                verdict_headline=translated(
                    verdict.verdict_headline, "verdict.verdict_headline"
                ),
                risk_level=translated(verdict.risk_level, "verdict.risk_level"),
                top_reason=translated(verdict.top_reason, "verdict.top_reason"),
                next_step=translated(verdict.next_step, "verdict.next_step"),
            ),
            warnings,
        )

    def adapt(self, script: ShortScript, locale: str) -> ShortScript:
        """Retain the old boundary while making unsupported locale behavior safe."""

        resolved = self.resolve(locale)
        if resolved.resolved_locale == "en-US":
            return script
        return script
