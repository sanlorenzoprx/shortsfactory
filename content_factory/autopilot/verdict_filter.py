from __future__ import annotations

import re

from .autopilot_models import BusinessIdeaCandidate, VerdictDecision, VerdictRecord


CREATED_AT = "2026-06-29T00:03:00+00:00"
GENERIC = ("do more research", "talk to users", "build an mvp", "market it better", "use social media")
CERTAINTY = ("guaranteed", "definitely work", "100% chance", "risk-free", "everyone needs")
STATS = re.compile(r"\b(?:market size|cagr|research shows|studies show)\b|\$\s*\d+\s*(?:million|billion)|\d+(?:\.\d+)?%\s+(?:growth|of)", re.I)


class VerdictQualityFilter:
    def filter(
        self,
        verdicts: list[VerdictRecord],
        ideas: list[BusinessIdeaCandidate],
        *,
        minimum_score: int,
        strict_rich_verdict: bool,
    ) -> list[VerdictDecision]:
        idea_map = {idea.idea_id: idea for idea in ideas}
        decisions = []
        for record in verdicts:
            idea = idea_map[record.idea_id]
            verdict = record.verdict
            required = all(
                verdict.get(field) not in (None, "")
                for field in ("verdict_headline", "lit_score", "risk_level", "top_reason", "next_step")
            )
            warnings = [str(value) for value in verdict.get("warnings", []) if value]
            combined = " ".join(str(verdict.get(field, "")) for field in (
                "verdict_headline", "top_reason", "next_step", "why_it_might_work",
                "why_it_might_fail", "killer_question", "mvp_test",
            )).casefold()
            reasons = []
            score = int(verdict.get("lit_score", 0) or 0)
            if not required:
                reasons.append("verdict missing required fields")
            if score < minimum_score:
                reasons.append(f"LIT score {score} is below {minimum_score}")
            if len(idea.target_user.strip()) < 5 or len(idea.angle.strip()) < 10:
                reasons.append("idea has no clear buyer or pain angle")
            if len(str(verdict.get("next_step", ""))) < 20 or any(value in combined for value in GENERIC):
                reasons.append("verdict action is too generic")
            if any(value in combined for value in CERTAINTY) or STATS.search(combined):
                reasons.append("verdict contains unsupported certainty or claims")
            provenance = verdict.get("provenance", {})
            if strict_rich_verdict and not (isinstance(provenance, dict) and provenance.get("rich_verdict") is True):
                reasons.append("strict rich verdict provenance is missing")
            decision = "reject" if reasons else "accept"
            decisions.append(VerdictDecision(
                idea_id=record.idea_id,
                job_id=None,
                lit_score=score,
                risk_level=str(verdict.get("risk_level", "unknown")),
                decision=decision,
                reason="; ".join(reasons) if reasons else "specific buyer, testable action, and score meet policy",
                minimum_score=minimum_score,
                required_fields_present=required,
                warnings=tuple(warnings),
                created_at=CREATED_AT,
            ))
        return decisions
