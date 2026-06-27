from __future__ import annotations

import hashlib

from content_factory.config import Config
from content_factory.integrations.lit_client import LitClient
from content_factory.schemas import AppTestOutcome, Idea, LitVerdict
from content_factory.utils.validation import normalize_lit_response


class AppTester:
    """Runs ideas through LIT.

    MVP rule: mock mode must always work offline. API mode is allowed to fail
    safely back into a complete mock verdict.
    """

    def __init__(self, config: Config):
        self.config = config
        self.client = LitClient(
            url=config.lit_api_url,
            timeout_seconds=config.lit_api_timeout_seconds,
            api_key=config.lit_api_key,
        )

    def run_test(self, idea: Idea, locale: str = "en-US") -> LitVerdict:
        return self.run_test_with_details(idea, locale=locale).verdict

    def run_test_with_details(self, idea: Idea, locale: str = "en-US") -> AppTestOutcome:
        if self.config.mode == "api":
            try:
                raw_response = self.client.test_idea(idea, locale=locale)
                normalized = normalize_lit_response(raw_response)
                verdict = LitVerdict(
                    idea=idea,
                    verdict_headline=normalized["verdict_headline"],
                    lit_score=normalized["lit_score"],
                    risk_level=normalized["risk_level"],
                    top_reason=normalized["top_reason"],
                    next_step=normalized["next_step"],
                    source=normalized["source"],
                )
                return AppTestOutcome(verdict=verdict, raw_response=raw_response)
            except Exception as exc:
                warning = self._fallback_warning(exc)
                return AppTestOutcome(
                    verdict=self._mock_verdict(idea, source="api_fallback"),
                    warning=warning,
                )
        return AppTestOutcome(verdict=self._mock_verdict(idea, source="mock"))

    def _mock_verdict(self, idea: Idea, source: str) -> LitVerdict:
        digest = hashlib.sha256(idea.name.encode("utf-8")).hexdigest()
        score = 55 + (int(digest[:2], 16) % 31)  # deterministic 55-85
        if score >= 78:
            headline = "Build a tiny test now"
            risk = "medium"
            reason = "The idea has a clear buyer, but the first offer must be narrow."
            next_step = "Pre-sell one painful use case before building a full product."
        elif score >= 65:
            headline = "Promising, but niche down"
            risk = "medium-high"
            reason = "The market is real, but the positioning is too broad."
            next_step = "Pick one urgent buyer and one painful job-to-be-done."
        else:
            headline = "Ghost town risk"
            risk = "high"
            reason = "The idea sounds attractive, but demand proof is weak."
            next_step = "Run interviews and collect willingness-to-pay signals first."
        return LitVerdict(
            idea=idea,
            verdict_headline=headline,
            lit_score=score,
            risk_level=risk,
            top_reason=reason,
            next_step=next_step,
            source=source,
        )

    @staticmethod
    def _fallback_warning(exc: Exception) -> str:
        details = " ".join(str(exc).split()) or "no error details"
        details = details[:300]
        return f"LIT API unavailable or invalid; used deterministic fallback ({type(exc).__name__}: {details})"
