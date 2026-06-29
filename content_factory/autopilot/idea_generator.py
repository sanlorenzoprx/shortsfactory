from __future__ import annotations

import hashlib
import re

from content_factory.schemas import Idea

from .autopilot_models import BusinessIdeaCandidate, TrendSignal


CREATED_AT = "2026-06-29T00:01:00+00:00"


class TrendIdeaGenerator:
    def generate(self, trends: list[TrendSignal], *, ideas_per_trend: int = 1, limit: int | None = None) -> list[BusinessIdeaCandidate]:
        if ideas_per_trend < 1:
            raise ValueError("ideas_per_trend must be positive")
        ideas: list[BusinessIdeaCandidate] = []
        for trend in trends:
            for variant in range(ideas_per_trend):
                title = " ".join(word.capitalize() for word in re.findall(r"[a-z0-9]+", trend.topic))
                target = self._target_user(trend.topic)
                angle = self._angle(trend)
                digest = hashlib.sha256(f"{trend.trend_id}:{variant}:{trend.topic}".encode("utf-8")).hexdigest()[:10]
                suffix = " Workflow" if variant == 0 else f" Experiment {variant + 1}"
                ideas.append(BusinessIdeaCandidate(
                    idea_id=f"idea_{digest}",
                    source_trend_id=trend.trend_id,
                    name=f"{title}{suffix}",
                    description=(
                        f"A focused workflow product for {target} that captures the evidence, follow-up, and handoff steps around {trend.topic}. "
                        f"The initial offer tests whether solving {angle} earns a paid pilot before software automation."
                    ),
                    target_user=target,
                    market=trend.market,
                    locale=trend.locale,
                    angle=angle,
                    why_now=f"The recorded {trend.source} signal is {trend.velocity}; evidence is limited to the stored trend receipt.",
                    constraints=("no unsupported market-size claims", "validate willingness to pay before building"),
                    created_at=CREATED_AT,
                ))
                if limit is not None and len(ideas) >= limit:
                    return ideas
        return ideas

    @staticmethod
    def _target_user(topic: str) -> str:
        lowered = topic.casefold()
        if "contractor" in lowered or "inspection" in lowered or "field service" in lowered:
            return "small specialty contractors"
        if "appointment" in lowered or "clinic" in lowered:
            return "owner-operated local service practices"
        return "small service business owners"

    @staticmethod
    def _angle(trend: TrendSignal) -> str:
        evidence = trend.evidence[0].get("value") if trend.evidence else trend.topic
        return str(evidence).strip() or trend.topic


def candidate_to_idea(candidate: BusinessIdeaCandidate) -> Idea:
    return Idea(
        name=candidate.name,
        description=candidate.description,
        target_user=candidate.target_user,
        market=candidate.market,
    )
