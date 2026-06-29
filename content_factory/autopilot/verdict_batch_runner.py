from __future__ import annotations

from dataclasses import asdict

from content_factory.agents.app_tester import AppTester
from content_factory.config import Config

from .autopilot_models import BusinessIdeaCandidate, VerdictRecord
from .idea_generator import candidate_to_idea


CREATED_AT = "2026-06-29T00:02:00+00:00"


class VerdictBatchRunner:
    def run(self, ideas: list[BusinessIdeaCandidate], *, mode: str = "mock") -> list[VerdictRecord]:
        tester = AppTester(Config(mode=mode))
        records = []
        for candidate in ideas:
            outcome = tester.run_test_with_details(candidate_to_idea(candidate), locale=candidate.locale)
            records.append(VerdictRecord(
                idea_id=candidate.idea_id,
                verdict=asdict(outcome.verdict),
                warning=outcome.warning,
                created_at=CREATED_AT,
            ))
        return records
