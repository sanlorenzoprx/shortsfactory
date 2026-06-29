from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_factory.autopilot.analytics_adapters import SimulatedAnalyticsAdapter
from content_factory.autopilot.autopilot_config import AutopilotConfig, AutopilotRefusal
from content_factory.autopilot.autopilot_models import (
    GateResult,
    PublishAttempt,
    VerdictRecord,
)
from content_factory.autopilot.autopilot_runner import AutopilotRunner
from content_factory.autopilot.autopilot_store import ARTIFACTS, AutopilotStore
from content_factory.autopilot.gates import MachineGates
from content_factory.autopilot.idea_generator import TrendIdeaGenerator
from content_factory.autopilot.learning_loop import LearningLoop
from content_factory.autopilot.publisher_adapters import (
    RefusingLivePublisherAdapter,
    SimulatedPublisherAdapter,
)
from content_factory.autopilot.trend_providers import MockTrendProvider
from content_factory.autopilot.verdict_filter import VerdictQualityFilter


FIXED = "2026-06-29T12:00:00+00:00"


class FakeContentRunner:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, accepted, ideas, verdicts, *, batch_id, config):
        self.calls += 1
        rows = []
        for index, decision in enumerate(accepted):
            job_id = f"fake{index:03d}"
            job_dir = Path(config.output_root) / "jobs" / job_id
            publisher = job_dir / "publish" / "publisher_plan.json"
            publisher.parent.mkdir(parents=True, exist_ok=True)
            receipt = job_dir / "receipt.json"
            receipt.write_text(json.dumps({
                "job_id": job_id,
                "verdict_provenance": {"source": "deterministic_mock", "validated": True},
                "verdict": {"verdict_headline": "Test a narrow paid workflow"},
                "publishing_status": "not_published",
                "live_publishing_enabled": False,
            }), encoding="utf-8")
            publisher.write_text(json.dumps({
                "publishing_status": "not_published",
                "live_publishing_enabled": False,
                "api_upload_attempted": False,
            }), encoding="utf-8")
            (job_dir / "script.txt").write_text("Hook: test one buyer pain.\nCTA: validate a paid pilot.", encoding="utf-8")
            rows.append({
                "job_id": job_id,
                "idea_id": decision.idea_id,
                "receipt_path": str(receipt.resolve()),
                "job_dir": str(job_dir.resolve()),
                "publisher_plan": str(publisher.resolve()),
            })
        return rows


class PassingGates:
    @staticmethod
    def _rows(name, jobs):
        return [GateResult(
            job_id=job["job_id"], gate_name=name, status="pass", blocking=False,
            reason=f"{name} passed", source_artifacts=(job["receipt_path"],),
            created_at=FIXED, details={"overall_score": 95} if name == "quality" else {},
        ) for job in jobs]

    def quality(self, jobs, config):
        return self._rows("quality", jobs)

    def compliance(self, jobs, config):
        return self._rows("compliance", jobs)


def _attempt(**overrides):
    values = {
        "publish_attempt_id": "pub_test",
        "batch_id": "ap_test_batch",
        "job_id": "job-test",
        "platform": "youtube_shorts",
        "mode": "dry_run",
        "adapter": "simulated",
        "status": "queued",
        "external_post_id": None,
        "external_url": None,
        "blocked_reason": None,
        "metadata_path": "publisher_plan.json",
        "created_at": FIXED,
        "finished_at": None,
    }
    values.update(overrides)
    return PublishAttempt(**values)


def test_mock_trends_and_ideas_are_deterministic():
    provider = MockTrendProvider()
    first = provider.collect(query="business pain", market="US", locale="en-US", limit=2)
    second = provider.collect(query="business pain", market="US", locale="en-US", limit=2)
    assert first == second
    assert all(row.source == "mock" for row in first)
    ideas = TrendIdeaGenerator().generate(first, limit=2)
    assert len(ideas) == 2
    assert all(idea.source_trend_id for idea in ideas)
    assert all("paid pilot" in idea.description for idea in ideas)


def test_mock_trend_provider_is_deterministic():
    provider = MockTrendProvider()
    arguments = {"query": "business searches", "market": "US", "locale": "en-US", "limit": 3}
    assert provider.collect(**arguments) == provider.collect(**arguments)


def test_idea_generator_is_deterministic_for_same_trends():
    trends = MockTrendProvider().collect(query="business searches", market="US", locale="en-US", limit=2)
    generator = TrendIdeaGenerator()
    assert generator.generate(trends) == generator.generate(trends)


def test_weak_verdict_is_rejected():
    trend = MockTrendProvider().collect(query="test", market="US", locale="en-US", limit=1)
    idea = TrendIdeaGenerator().generate(trend, limit=1)[0]
    weak = VerdictRecord(idea_id=idea.idea_id, created_at=FIXED, warning=None, verdict={
        "verdict_headline": "Maybe",
        "lit_score": 22,
        "risk_level": "high",
        "top_reason": "Demand is unclear.",
        "next_step": "Do more research.",
    })
    decision = VerdictQualityFilter().filter(
        [weak], [idea], minimum_score=55, strict_rich_verdict=False,
    )[0]
    assert decision.decision == "reject"
    assert "below 55" in decision.reason
    assert "too generic" in decision.reason


def test_quality_and_compliance_gates_block_unsafe_output(tmp_path, monkeypatch):
    output = tmp_path / "output with spaces"
    job_dir = output / "jobs" / "unsafe-job"
    publisher = job_dir / "publish" / "publisher_plan.json"
    publisher.parent.mkdir(parents=True)
    receipt = job_dir / "receipt.json"
    receipt.write_text(json.dumps({
        "verdict_provenance": {"source": "mock"},
        "verdict": {},
        "live_publishing_enabled": False,
    }), encoding="utf-8")
    publisher.write_text(json.dumps({"live_publishing_enabled": False}), encoding="utf-8")
    (job_dir / "script.txt").write_text("{{UNRESOLVED}} guaranteed results", encoding="utf-8")
    job = {
        "job_id": "unsafe-job",
        "job_dir": str(job_dir),
        "receipt_path": str(receipt),
        "publisher_plan": str(publisher),
    }

    monkeypatch.setattr("content_factory.autopilot.gates.evaluate_job", lambda *_: {
        "overall_score": 42,
        "issues": [],
        "present_artifacts": ["short.mp4", "thumbnail.jpg", "receipt.json"],
    })
    config = AutopilotConfig(output_root=output, minimum_quality_score=80)
    quality = MachineGates().quality([job], config)[0]
    compliance = MachineGates().compliance([job], config)[0]
    assert quality.blocking is True
    assert compliance.blocking is True
    assert "placeholder" in compliance.reason
    assert "fake certainty" in compliance.reason


def test_autopilot_blocks_below_quality_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("content_factory.autopilot.gates.evaluate_job", lambda *_: {
        "overall_score": 79,
        "issues": [],
        "present_artifacts": ["short.mp4", "thumbnail.jpg", "receipt.json"],
    })
    config = AutopilotConfig(output_root=tmp_path, minimum_quality_score=80)
    result = MachineGates().quality([{"job_id": "weak", "receipt_path": "receipt.json"}], config)[0]
    assert result.status == "fail"
    assert result.blocking is True


def test_autopilot_blocks_unresolved_placeholders(tmp_path):
    job_dir = tmp_path / "jobs" / "placeholder"
    publisher = job_dir / "publish" / "publisher_plan.json"
    publisher.parent.mkdir(parents=True)
    receipt = job_dir / "receipt.json"
    receipt.write_text(json.dumps({
        "verdict_provenance": {"source": "mock"},
        "verdict": {},
        "live_publishing_enabled": False,
    }), encoding="utf-8")
    publisher.write_text(json.dumps({"live_publishing_enabled": False}), encoding="utf-8")
    (job_dir / "script.txt").write_text("Hook: {{IDEA_NAME}}", encoding="utf-8")
    result = MachineGates().compliance([{
        "job_id": "placeholder", "job_dir": str(job_dir),
        "receipt_path": str(receipt), "publisher_plan": str(publisher),
    }], AutopilotConfig(output_root=tmp_path))[0]
    assert result.status == "fail"
    assert "placeholder" in result.reason


def test_dry_run_adapters_never_publish_or_fetch_live():
    attempt = _attempt()
    adapter = SimulatedPublisherAdapter("youtube_shorts")
    assert adapter.preflight(config=AutopilotConfig()) == {
        "ready": True,
        "adapter": "simulated",
        "credentials_required": False,
        "live_publishing_enabled": False,
    }
    result = adapter.publish(attempt=attempt, package={"metadata_path": attempt.metadata_path})
    assert result.status == "simulated_success"
    assert result.external_post_id is None
    assert result.external_url is None
    snapshot = SimulatedAnalyticsAdapter("youtube_shorts").collect(published_item=result)
    assert snapshot.source == "simulated"
    assert snapshot.metrics["views"] > 0

    with pytest.raises(AutopilotRefusal, match="Live publishing is not implemented"):
        RefusingLivePublisherAdapter("youtube_shorts").publish(attempt=attempt, package={})
    with pytest.raises(AutopilotRefusal, match="Live publishing is not implemented"):
        AutopilotConfig(mode="full_autopilot").assert_phase_5a_runnable()
    with pytest.raises(AutopilotRefusal, match="placeholder"):
        AutopilotConfig(mode="supervised_autopilot").assert_phase_5a_runnable()


def test_simulated_analytics_is_deterministic_for_same_publish_attempt():
    published = _attempt(status="simulated_success")
    adapter = SimulatedAnalyticsAdapter("youtube_shorts")
    assert adapter.collect(published_item=published) == adapter.collect(published_item=published)


def test_autopilot_rejects_scraping_provider():
    with pytest.raises(AutopilotRefusal, match="Scraping"):
        AutopilotConfig(trend_provider="scraping_search").assert_phase_5a_runnable()


def test_autopilot_rejects_missing_credentials_for_live_adapter():
    adapter = RefusingLivePublisherAdapter("youtube_shorts")
    preflight = adapter.preflight(config=AutopilotConfig())
    assert preflight["ready"] is False
    assert preflight["credentials_required"] is True
    with pytest.raises(AutopilotRefusal, match="Live publishing is not implemented"):
        adapter.publish(attempt=_attempt(), package={})


def test_autopilot_does_not_commit_runtime_outputs():
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert "output/" in ignored


def test_learning_loop_recommendation_is_deterministic():
    trends = MockTrendProvider().collect(query="test", market="US", locale="en-US", limit=1)
    ideas = TrendIdeaGenerator().generate(trends, limit=1)
    arguments = {
        "batch_id": "ap_learning_test",
        "performance": {"top_jobs": []},
        "trends": trends,
        "ideas": ideas,
        "jobs": [],
        "batch_size": 3,
    }
    loop = LearningLoop()
    assert loop.recommend(**arguments) == loop.recommend(**arguments)


def test_complete_cycle_writes_all_receipts_and_can_resume(tmp_path):
    output = tmp_path / "output root with spaces"
    store = AutopilotStore(output)
    content = FakeContentRunner()
    runner = AutopilotRunner(store=store, content_runner=content, gates=PassingGates())
    config = AutopilotConfig(
        output_root=output,
        batch_id="ap_test_complete",
        created_at=FIXED,
        batch_size=2,
        trend_limit=2,
    )
    receipt = runner.run_cycle(config)

    assert receipt["status"] == "completed"
    assert receipt["safety"] == {
        "dry_run": True,
        "live_publishing_enabled": False,
        "live_publish_attempted": False,
        "platform_api_calls_attempted": False,
        "scraping_attempted": False,
        "browser_posting_attempted": False,
        "credentials_used": False,
        "simulated_publishing_only": True,
        "simulated_analytics_only": True,
    }
    assert receipt["counts"]["generated_jobs"] == 2
    assert receipt["counts"]["simulated_publish_successes"] == 6
    assert set(receipt["machine_path"]) == {
        "trend_discovery", "idea_generation", "lit_verdict", "verdict_filter",
        "short_generation", "quality_gate", "compliance_gate", "simulated_publish",
        "simulated_analytics", "performance_review", "next_batch_plan",
    }
    assert all(store.exists(config.batch_id, key) for key in ARTIFACTS)
    attempts = store.read(config.batch_id, "publish")
    assert all(row["adapter"] == "simulated" for row in attempts)
    assert all(row["external_url"] is None for row in attempts)
    performance = store.read(config.batch_id, "performance")
    assert performance["source"]["kind"] == "simulated_analytics"
    assert all(row["type"] != "manual_experiment" for row in performance["recommendations"])

    trends_before = store.path(config.batch_id, "trends").read_bytes()
    resumed = runner.resume(config.batch_id)
    assert resumed == receipt
    assert content.calls == 1
    assert store.path(config.batch_id, "trends").read_bytes() == trends_before


def test_resume_continues_from_existing_stage_receipts(tmp_path):
    output = tmp_path / "output"
    store = AutopilotStore(output)
    content = FakeContentRunner()
    runner = AutopilotRunner(store=store, content_runner=content, gates=PassingGates())
    config = AutopilotConfig(
        output_root=output,
        batch_id="ap_test_resume",
        created_at=FIXED,
        batch_size=1,
        trend_limit=1,
    )
    runner.run_cycle(config)
    store.path(config.batch_id, "receipt").unlink()
    store.path(config.batch_id, "next_plan").unlink()
    jobs_before = store.path(config.batch_id, "jobs").read_bytes()

    receipt = runner.resume(config.batch_id)
    assert receipt["status"] == "completed"
    assert content.calls == 1
    assert store.path(config.batch_id, "jobs").read_bytes() == jobs_before
    assert store.exists(config.batch_id, "next_plan")
