from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_factory.performance.performance_metrics import build_performance_review

from .analytics_adapters import SimulatedAnalyticsAdapter
from .autopilot_config import AutopilotConfig
from .autopilot_models import (
    AnalyticsSnapshot,
    BusinessIdeaCandidate,
    GateResult,
    PublishAttempt,
    TrendSignal,
    VerdictDecision,
    VerdictRecord,
)
from .autopilot_store import AutopilotStore
from .batch_planner import build_batch_plan
from .content_batch_runner import ContentBatchRunner
from .gates import MachineGates
from .idea_generator import TrendIdeaGenerator
from .learning_loop import LearningLoop
from .publisher_adapters import SimulatedPublisherAdapter, build_publish_queue
from .receipts import build_autopilot_receipt
from .trend_providers import FileTrendProvider, MockTrendProvider, TrendProvider
from .verdict_batch_runner import VerdictBatchRunner
from .verdict_filter import VerdictQualityFilter


class AutopilotRunner:
    def __init__(
        self,
        *,
        store: AutopilotStore | None = None,
        trend_provider: TrendProvider | None = None,
        idea_generator: TrendIdeaGenerator | None = None,
        verdict_runner: VerdictBatchRunner | None = None,
        verdict_filter: VerdictQualityFilter | None = None,
        content_runner: ContentBatchRunner | None = None,
        gates: MachineGates | None = None,
        learning_loop: LearningLoop | None = None,
    ):
        self.store = store
        self.trend_provider = trend_provider
        self.idea_generator = idea_generator or TrendIdeaGenerator()
        self.verdict_runner = verdict_runner or VerdictBatchRunner()
        self.verdict_filter = verdict_filter or VerdictQualityFilter()
        self.content_runner = content_runner or ContentBatchRunner()
        self.gates = gates or MachineGates()
        self.learning_loop = learning_loop or LearningLoop()

    def run_cycle(self, config: AutopilotConfig, *, resume: bool = False) -> dict[str, Any]:
        config.assert_phase_5a_runnable()
        store = self.store or AutopilotStore(config.output_root)
        self.store = store
        batch_id = config.batch_id or store.new_batch_id()
        created_at = config.created_at or store.now()

        if resume and store.exists(batch_id, "receipt"):
            return store.read(batch_id, "receipt")
        if store.exists(batch_id, "plan"):
            plan = store.read(batch_id, "plan")
        else:
            plan = build_batch_plan(batch_id, config, created_at)
            store.write(batch_id, "plan", plan)
        plan["status"] = "running"
        store.write(batch_id, "plan", plan)

        trends = self._stage_models(
            batch_id, "trends", TrendSignal,
            lambda: self._provider(config).collect(
                query=config.trend_query, market=config.market, locale=config.locale,
                limit=config.trend_limit,
            ),
        )
        self._complete(plan, "trends", store)

        ideas = self._stage_models(
            batch_id, "ideas", BusinessIdeaCandidate,
            lambda: self.idea_generator.generate(
                trends, ideas_per_trend=config.ideas_per_trend, limit=config.batch_size,
            ),
        )
        self._complete(plan, "ideas", store)

        verdicts = self._stage_models(
            batch_id, "verdicts", VerdictRecord,
            lambda: self.verdict_runner.run(ideas, mode=config.lit_mode),
        )
        self._complete(plan, "verdicts", store)

        decisions = self._stage_models(
            batch_id, "decisions", VerdictDecision,
            lambda: self.verdict_filter.filter(
                verdicts, ideas, minimum_score=config.minimum_lit_score,
                strict_rich_verdict=config.strict_rich_verdict,
            ),
        )
        self._complete(plan, "decisions", store)
        accepted = [decision for decision in decisions if decision.decision == "accept"][:config.batch_size]

        jobs = self._stage_dicts(
            batch_id, "jobs",
            lambda: self.content_runner.generate(
                accepted, ideas, verdicts, batch_id=batch_id, config=config,
            ),
        )
        self._complete(plan, "jobs", store)

        quality = self._stage_models(
            batch_id, "quality", GateResult,
            lambda: self.gates.quality(jobs, config),
        )
        self._complete(plan, "quality", store)
        compliance = self._stage_models(
            batch_id, "compliance", GateResult,
            lambda: self.gates.compliance(jobs, config),
        )
        self._complete(plan, "compliance", store)
        plan["status"] = "gated"
        store.write(batch_id, "plan", plan)

        queue = self._stage_models(
            batch_id, "publish_queue", PublishAttempt,
            lambda: build_publish_queue(
                batch_id=batch_id, jobs=jobs,
                quality=[row.to_dict() for row in quality],
                compliance=[row.to_dict() for row in compliance], config=config,
            ),
        )
        self._complete(plan, "publish_queue", store)
        attempts = self._stage_models(
            batch_id, "publish", PublishAttempt,
            lambda: self._simulate_publish(queue, config),
        )
        self._complete(plan, "publish", store)
        plan["status"] = "simulated_published"
        store.write(batch_id, "plan", plan)

        analytics = self._stage_models(
            batch_id, "analytics", AnalyticsSnapshot,
            lambda: [
                SimulatedAnalyticsAdapter(attempt.platform).collect(published_item=attempt)
                for attempt in attempts if attempt.status == "simulated_success"
            ],
        )
        self._complete(plan, "analytics", store)

        performance = self._stage_dict(
            batch_id, "performance",
            lambda: self._performance(analytics, jobs, quality, compliance, created_at),
        )
        self._complete(plan, "performance", store)
        next_plan = self._stage_dict(
            batch_id, "next_plan",
            lambda: self.learning_loop.recommend(
                batch_id=batch_id, performance=performance, trends=trends, ideas=ideas,
                jobs=jobs, batch_size=config.batch_size,
            ).to_dict(),
        )
        self._complete(plan, "next_plan", store)

        counts = {
            "trends": len(trends), "ideas": len(ideas), "accepted_ideas": len(accepted),
            "generated_jobs": len(jobs),
            "quality_passed": sum(row.status == "pass" for row in quality),
            "compliance_passed": sum(row.status == "pass" for row in compliance),
            "simulated_publish_successes": sum(row.status == "simulated_success" for row in attempts),
            "analytics_snapshots": len(analytics),
        }
        receipt = build_autopilot_receipt(
            store=store, batch_id=batch_id, mode=config.mode,
            created_at=created_at, counts=counts,
        )
        store.write(batch_id, "receipt", receipt)
        plan.update({
            "status": "completed", "trend_count": len(trends), "idea_count": len(ideas),
            "accepted_idea_count": len(accepted), "completed_at": receipt["completed_at"],
        })
        self._complete(plan, "receipt", store)
        return receipt

    def resume(self, batch_id: str) -> dict[str, Any]:
        if self.store is None:
            raise ValueError("resume requires a configured store")
        plan = self.store.read(batch_id, "plan")
        config = AutopilotConfig.from_dict({**plan["config"], "batch_id": batch_id})
        return self.run_cycle(config, resume=True)

    def _provider(self, config: AutopilotConfig) -> TrendProvider:
        if self.trend_provider is not None:
            if "scrap" in self.trend_provider.key.casefold():
                raise ValueError("Scraping trend providers are forbidden in Phase 5A.")
            return self.trend_provider
        if config.trend_file is not None:
            return FileTrendProvider(config.trend_file)
        return MockTrendProvider()

    def _complete(self, plan: dict[str, Any], stage: str, store: AutopilotStore) -> None:
        if stage not in plan["completed_stages"]:
            plan["completed_stages"].append(stage)
        store.write(plan["batch_id"], "plan", plan)

    def _stage_models(self, batch_id: str, name: str, model, build):
        if self.store.exists(batch_id, name):
            return [model.from_dict(value) for value in self.store.read(batch_id, name)]
        values = build()
        self.store.write(batch_id, name, [value.to_dict() for value in values])
        return values

    def _stage_dicts(self, batch_id: str, name: str, build):
        if self.store.exists(batch_id, name):
            return list(self.store.read(batch_id, name))
        values = build()
        self.store.write(batch_id, name, values)
        return values

    def _stage_dict(self, batch_id: str, name: str, build):
        if self.store.exists(batch_id, name):
            return dict(self.store.read(batch_id, name))
        value = build()
        self.store.write(batch_id, name, value)
        return value

    @staticmethod
    def _simulate_publish(queue: list[PublishAttempt], config: AutopilotConfig) -> list[PublishAttempt]:
        results = []
        for attempt in queue:
            if attempt.status != "queued":
                results.append(attempt)
                continue
            adapter = SimulatedPublisherAdapter(attempt.platform)
            if adapter.preflight(config=config)["ready"] is not True:
                results.append(PublishAttempt(**{**attempt.to_dict(), "status": "blocked", "blocked_reason": "simulated publisher preflight failed"}))
                continue
            results.append(adapter.publish(attempt=attempt, package={"metadata_path": attempt.metadata_path}))
        return results

    @staticmethod
    def _performance(
        analytics: list[AnalyticsSnapshot], jobs: list[dict[str, str]],
        quality: list[GateResult], compliance: list[GateResult], created_at: str,
    ) -> dict[str, Any]:
        job_map = {job["job_id"]: job for job in jobs}
        quality_map = {row.job_id: row for row in quality}
        compliance_map = {row.job_id: row for row in compliance}
        entries = []
        for snapshot in analytics:
            receipt = json.loads(Path(job_map[snapshot.job_id]["receipt_path"]).read_text(encoding="utf-8"))
            templates = receipt.get("templates", {}) if isinstance(receipt.get("templates"), dict) else {}
            entries.append({
                "entry_id": snapshot.snapshot_id,
                "created_at": snapshot.captured_at,
                "job_id": snapshot.job_id,
                "platform": snapshot.platform,
                "metrics": dict(snapshot.metrics),
                "context": {
                    "quality_score": quality_map[snapshot.job_id].details.get("overall_score"),
                    "compliance_status": compliance_map[snapshot.job_id].status,
                    "template_ids": {
                        key: value.get("template_id") for key, value in templates.items()
                        if isinstance(value, dict) and value.get("template_id")
                    },
                },
                "notes": "simulated Phase 5A analytics",
                "lessons": [],
            })
        review = build_performance_review(entries, results_root="simulated_analytics", created_at=created_at)
        review["source"] = {"kind": "simulated_analytics", "entry_count": len(entries)}
        review["safety"] = {
            "simulated_analytics_only": True,
            "api_fetch_attempted": False,
            "scraping_attempted": False,
            "live_publishing_enabled": False,
        }
        for recommendation in review.get("recommendations", []):
            if recommendation.get("type") == "manual_experiment":
                recommendation["type"] = "autopilot_experiment"
            recommendation["message"] = str(recommendation.get("message", "")).replace("manual result", "simulated result")
        return review
