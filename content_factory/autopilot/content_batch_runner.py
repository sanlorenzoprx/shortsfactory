from __future__ import annotations

import hashlib
from pathlib import Path

from content_factory.config import Config
from content_factory.schemas import Idea, LitVerdict
from orchestrator import ContentFactoryOrchestrator

from .autopilot_config import AutopilotConfig
from .autopilot_models import BusinessIdeaCandidate, VerdictDecision, VerdictRecord
from .idea_generator import candidate_to_idea


class ContentBatchRunner:
    def generate(
        self,
        accepted: list[VerdictDecision],
        ideas: list[BusinessIdeaCandidate],
        verdicts: list[VerdictRecord],
        *,
        batch_id: str,
        config: AutopilotConfig,
    ) -> list[dict[str, str]]:
        idea_map = {idea.idea_id: idea for idea in ideas}
        verdict_map = {verdict.idea_id: verdict for verdict in verdicts}
        jobs = []
        for decision in accepted:
            candidate = idea_map[decision.idea_id]
            verdict = self._lit_verdict(verdict_map[decision.idea_id].verdict, candidate_to_idea(candidate))
            digest = hashlib.sha256(f"{batch_id}:{candidate.idea_id}".encode("utf-8")).hexdigest()[:10]
            job_id = f"ap{digest}"
            generator = ContentFactoryOrchestrator(Config(
                mode=config.lit_mode,
                output_dir=config.output_root,
                publish_dry_run_enabled=True,
            ))
            receipt_path = generator.run_batch(
                batch=1,
                locale=candidate.locale,
                job_id=job_id,
                ideas=[candidate_to_idea(candidate)],
                verdicts=[verdict],
            )[0]
            receipt = receipt_path.resolve()
            jobs.append({
                "job_id": job_id,
                "idea_id": candidate.idea_id,
                "receipt_path": str(receipt),
                "job_dir": str(receipt.parent),
                "publisher_plan": str((receipt.parent / "publish" / "publisher_plan.json").resolve()),
            })
        return jobs

    @staticmethod
    def _lit_verdict(value: dict, idea: Idea) -> LitVerdict:
        fields = {
            "verdict_headline": str(value.get("verdict_headline", "")),
            "lit_score": int(value.get("lit_score", 0)),
            "risk_level": str(value.get("risk_level", "unknown")),
            "top_reason": str(value.get("top_reason", "")),
            "next_step": str(value.get("next_step", "")),
            "source": str(value.get("source", "mock")),
            "ghost_town_risk": str(value.get("ghost_town_risk", "")),
            "buyer_pain_clarity": str(value.get("buyer_pain_clarity", "")),
            "willingness_to_pay_signal": str(value.get("willingness_to_pay_signal", "")),
            "distribution_difficulty": str(value.get("distribution_difficulty", "")),
            "unfair_advantage_check": str(value.get("unfair_advantage_check", "")),
            "business_model_weakness": str(value.get("business_model_weakness", "")),
            "why_it_might_work": str(value.get("why_it_might_work", "")),
            "why_it_might_fail": str(value.get("why_it_might_fail", "")),
            "killer_question": str(value.get("killer_question", "")),
            "mvp_test": str(value.get("mvp_test", "")),
            "provenance": dict(value.get("provenance", {})) if isinstance(value.get("provenance"), dict) else {},
            "warnings": tuple(value.get("warnings", [])) if isinstance(value.get("warnings"), (list, tuple)) else (),
        }
        return LitVerdict(idea=idea, **fields)
