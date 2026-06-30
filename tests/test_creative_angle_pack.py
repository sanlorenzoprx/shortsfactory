from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from content_factory.autopilot.autopilot_config import AutopilotConfig, AutopilotRefusal
from content_factory.autopilot.creative_angle_models import (
    AngleShortJob,
    CreativeAnglePack,
    CreativeAnglePackReceipt,
    LongFormAssemblyPlan,
)
from content_factory.autopilot.creative_angle_pack import CreativeAnglePackGenerator, main
from content_factory.autopilot.creative_providers import (
    CTA,
    CreativeProviderError,
    DeterministicCreativeGenerationProvider,
    FixtureCreativeGenerationProvider,
    OnlineLLMConfig,
)


FIXTURE = Path("fixtures/lit_verdicts/sample.json")
NOW = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)
EXPECTED_ANGLES = {
    "ghost_town_risk",
    "buyer_reality",
    "fast_validation_test",
    "contrarian_opportunity",
    "builder_action_plan",
}


def _generate(tmp_path: Path, provider=None):
    output = tmp_path / "output with spaces"
    generator = CreativeAnglePackGenerator(
        provider=provider or DeterministicCreativeGenerationProvider(),
        output_root=output,
        now=lambda: NOW,
    )
    receipt = generator.generate(lit_verdict_file=FIXTURE)
    return output, generator, receipt


def _artifacts(output: Path, receipt: CreativeAnglePackReceipt):
    pack = CreativeAnglePack.from_dict(json.loads((output / receipt.artifacts["creative_angle_pack"]).read_text(encoding="utf-8")))
    jobs = tuple(
        AngleShortJob.from_dict(json.loads((output / receipt.artifacts[f"short_{angle_id}"]).read_text(encoding="utf-8")))
        for angle_id in EXPECTED_ANGLES
    )
    longform = LongFormAssemblyPlan.from_dict(
        json.loads((output / receipt.artifacts["longform_plan"]).read_text(encoding="utf-8"))
    )
    return pack, jobs, longform


def test_deterministic_provider_generates_exactly_five_unique_angles(tmp_path):
    output, _, receipt = _generate(tmp_path)
    pack, jobs, _ = _artifacts(output, receipt)
    assert receipt.status == "completed"
    assert receipt.provider_type == "deterministic"
    assert receipt.network_called is False
    assert receipt.five_angles_generated is True
    assert receipt.short_jobs_created == 5
    assert len(pack.angles) == 5
    assert {angle.angle_id for angle in pack.angles} == EXPECTED_ANGLES
    assert len(jobs) == 5


def test_every_short_is_complete_and_references_same_lit_verdict(tmp_path):
    output, _, receipt = _generate(tmp_path)
    pack, jobs, _ = _artifacts(output, receipt)
    assert {job.lit_verdict_id for job in jobs} == {pack.lit_verdict_id}
    for job in jobs:
        assert all((job.title, job.hook, job.script, job.caption, job.thumbnail_text, job.cta))
        assert job.cta == CTA
        assert job.youtube_metadata_draft["angle_id"] == job.angle_id
        assert job.youtube_metadata_draft["cta"] == CTA
        assert job.tags and job.hashtags
        assert job.youtube_video_id is None
        assert job.upload_attempt_id is None
        assert job.verification_receipt is None
        assert job.analytics_receipt is None
        assert job.country_analytics_receipt is None
        assert job.performance_score is None
        assert job.data_quality == "pending"


def test_longform_plan_contains_all_five_shorts_and_canonical_cta(tmp_path):
    output, _, receipt = _generate(tmp_path)
    _, jobs, longform = _artifacts(output, receipt)
    assert receipt.longform_plan_created is True
    assert longform.source_short_job_ids == tuple(job.job_id for job in sorted(jobs, key=lambda row: next(
        index for index, chapter in enumerate(longform.ordered_chapters) if chapter["job_id"] == row.job_id
    )))
    assert {chapter["angle_id"] for chapter in longform.ordered_chapters} == EXPECTED_ANGLES
    assert len(longform.transition_lines) == 4
    assert len(longform.suggested_chapters_timestamps) == 6
    assert longform.cta_to_ghosttowntest_com == CTA


def test_fixture_provider_uses_checked_in_outputs_without_network(tmp_path, monkeypatch):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    network_calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: network_calls.append((args, kwargs)))
    output, _, receipt = _generate(
        tmp_path, FixtureCreativeGenerationProvider(fixture["creative_output"]),
    )
    pack, jobs, _ = _artifacts(output, receipt)
    assert receipt.status == "completed"
    assert receipt.provider_type == "fixture"
    assert receipt.network_called is False
    assert pack.provider_type == "fixture"
    assert {job.angle_id for job in jobs} == EXPECTED_ANGLES
    assert network_calls == []


def test_online_provider_refuses_missing_config_without_network(tmp_path, monkeypatch):
    for name in (
        "CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY", "CREATIVE_LLM_MODEL",
        "CREATIVE_LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(CreativeProviderError, match="requires CREATIVE_LLM_API_URL"):
        OnlineLLMConfig.load(config_path=tmp_path / "missing.json")
    assert calls == []


class UnselectedOnlineProvider(DeterministicCreativeGenerationProvider):
    provider_type = "online_llm"
    model_id = "must-not-run"

    def __init__(self):
        self.called = False

    def generate_angle_pack(self, context):
        self.called = True
        return super().generate_angle_pack(context)


def test_programmatic_online_provider_blocks_before_provider_call(tmp_path):
    provider = UnselectedOnlineProvider()
    _, _, receipt = _generate(tmp_path, provider)
    assert receipt.status == "blocked"
    assert receipt.network_called is False
    assert provider.called is False
    assert receipt.gates[0]["gate_name"] == "online_provider_explicit"


class UnsafeDeterministicProvider(DeterministicCreativeGenerationProvider):
    def generate_caption(self, context, angle):
        return super().generate_caption(context, angle) + " api_key=fixture-secret-never-store"


def test_failed_gate_writes_only_durable_redacted_receipt(tmp_path):
    output, generator, receipt = _generate(tmp_path, UnsafeDeterministicProvider())
    receipt_path = generator.receipt_path(receipt.angle_pack_id)
    persisted = receipt_path.read_text(encoding="utf-8")
    assert receipt.status == "blocked"
    assert receipt.artifacts == {}
    assert receipt.secrets_recorded is False
    assert "fixture-secret-never-store" not in persisted
    assert any(gate["gate_name"] == "secret_redaction" and gate["status"] == "fail" for gate in receipt.gates)
    assert list(generator.pack_dir(receipt.angle_pack_id).iterdir()) == [receipt_path]


def test_receipt_and_all_expected_artifacts_are_durable_and_redacted(tmp_path):
    output, generator, receipt = _generate(tmp_path)
    receipt_path = generator.receipt_path(receipt.angle_pack_id)
    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    CreativeAnglePackReceipt.from_dict(persisted)
    assert persisted["secrets_recorded"] is False
    assert persisted["publish_attempted"] is False
    assert persisted["safety"]["raw_provider_response_recorded"] is False
    assert all((output / relative).is_file() for relative in receipt.artifacts.values())
    assert len([key for key in receipt.artifacts if key.startswith("short_")]) == 5
    assert len([key for key in receipt.artifacts if key.startswith("script_")]) == 5


def test_generation_does_not_publish_or_enable_autopilot_modes(tmp_path):
    output, _, receipt = _generate(tmp_path)
    _, jobs, longform = _artifacts(output, receipt)
    assert receipt.publish_attempted is False
    assert receipt.safety["live_publishing_enabled"] is False
    assert receipt.safety["full_autopilot_enabled"] is False
    assert receipt.safety["supervised_autopilot_enabled"] is False
    assert all(job.live_publish_enabled is False for job in jobs)
    assert all(job.youtube_metadata_draft["status"] == "draft_not_upload_ready" for job in jobs)
    assert longform.live_publish_enabled is False
    with pytest.raises(AutopilotRefusal, match="Live publishing is not implemented"):
        AutopilotConfig(mode="full_autopilot").assert_phase_5a_runnable()
    with pytest.raises(AutopilotRefusal, match="placeholder"):
        AutopilotConfig(mode="supervised_autopilot").assert_phase_5a_runnable()


def test_cli_generates_deterministic_pack_and_reports_paths(tmp_path, capsys):
    result = main([
        "generate",
        "--lit-verdict-file", str(FIXTURE),
        "--provider", "deterministic",
        "--output-root", str(tmp_path / "output"),
    ])
    stdout = capsys.readouterr().out
    assert result == 0
    assert "Status: completed" in stdout
    assert "Short jobs: 5" in stdout
    assert "Long-form plan:" in stdout
    assert "Full autopilot enabled: false" in stdout
    assert "Supervised autopilot enabled: false" in stdout


def test_cli_online_mode_refuses_without_config(tmp_path, monkeypatch, capsys):
    for name in ("CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY", "CREATIVE_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    result = main([
        "generate",
        "--lit-verdict-file", str(FIXTURE),
        "--provider", "online_llm",
        "--model", "fixture-model",
        "--online-config", str(tmp_path / "missing.json"),
        "--output-root", str(tmp_path / "output"),
    ])
    stderr = capsys.readouterr().err
    assert result == 1
    assert "online_llm requires" in stderr
