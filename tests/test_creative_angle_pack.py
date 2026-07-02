from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from content_factory.autopilot.autopilot_config import AutopilotConfig, AutopilotRefusal
from content_factory.autopilot.creative_angle_models import (
    AngleShortJob,
    CreativeAnglePack,
    CreativeAnglePackReceipt,
    LongFormAssemblyPlan,
)
from content_factory.autopilot.creative_angle_pack import CreativeAnglePackGenerator, build_parser, main
from content_factory.autopilot.creative_fallback import CreativeFallbackRunner
from content_factory.autopilot.creative_pack_comparison import CreativePackComparator
from content_factory.autopilot.creative_providers import (
    CTA,
    DeterministicCreativeGenerationProvider,
    FixtureCreativeGenerationProvider,
    OnlineLLMCreativeGenerationProvider,
)
from content_factory.autopilot.llm_model_registry import LLMModelRegistry
from content_factory.autopilot.llm_provider_adapters import FakeLLMAdapter, GenericHTTPAdapter, build_llm_adapter
from content_factory.autopilot.llm_bundle_normalizer import normalize_llm_creative_bundle
from content_factory.autopilot.llm_bundle_schema import LLMBundleValidationError, LLMCreativeBundleV1
from content_factory.autopilot.verdict_grounding import (
    EXTERNAL_FACT_CATEGORIES,
    build_verdict_grounding_packet,
    classify_external_fact_signals,
    grounding_packet_diagnostics,
)


FIXTURE = Path("fixtures/lit_verdicts/sample.json")
NO_LOCAL_MODELS = Path("tests/fixtures/llm_models.none.json")
NOW = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)
EXPECTED_ANGLES = {
    "ghost_town_risk",
    "buyer_reality",
    "fast_validation_test",
    "contrarian_opportunity",
    "builder_action_plan",
}


def _generate(tmp_path: Path, provider=None, *, online_explicit=False):
    output = tmp_path / "output with spaces"
    generator = CreativeAnglePackGenerator(
        provider=provider or DeterministicCreativeGenerationProvider(),
        output_root=output,
        now=lambda: NOW,
        online_provider_explicit=online_explicit,
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


def _compact_bundle():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    creative = fixture["creative_output"]
    angles = []
    for spec in creative["angles"]:
        angle_id = spec["angle_id"]
        short = creative["shorts"][angle_id]
        metadata = short["youtube_metadata_draft"]
        angles.append({
            "angle_id": angle_id,
            "title": short["title_variants"][0],
            "hook": short["hook"],
            "script": short["script"],
            "caption": short["caption"],
            "thumbnail_text": short["thumbnail_text"],
            "tags": metadata["tags"],
            "hashtags": metadata["hashtags"],
        })
    longform = creative["longform"]
    return {
        "idea_summary": fixture["idea"]["description"],
        "verdict_summary": fixture["verdict"]["top_reason"],
        "cta": "Run your idea through the Ghost Town Test at GhostTownTest.com",
        "angles": angles,
        "longform": {
            "title": longform["longform_title"],
            "intro": longform["intro_script"],
            "chapters": [
                {
                    "angle_id": chapter["angle_id"],
                    "title": chapter["chapter_title"],
                    "summary": chapter["chapter_script"],
                }
                for chapter in longform["ordered_chapters"]
            ],
            "transitions": longform["transition_lines"],
            "conclusion": longform["conclusion"],
            "description": longform["suggested_description"],
        },
    }


def _compact_bundle_missing_script_caption_cta(marker: str = "quality-diagnostic-marker-must-not-store"):
    value = _compact_bundle()
    replacement = f"Run a validation check before building. {marker}"
    for angle in value["angles"]:
        angle["script"] = str(angle["script"]).replace(CTA, replacement)
        angle["caption"] = str(angle["caption"]).replace(CTA, replacement)
    return value


def _compact_bundle_missing_buyer_pain_action_signal(signal: str):
    value = _compact_bundle()
    if signal == "buyer":
        angle = value["angles"][0]
        angle["hook"] = "Ghost town risk reveals contractor proof failure when the market may not care"
        angle["script"] = "This urgent contractor proof risk can fail. Test and validate the assumption before building."
    elif signal == "pain":
        angle = value["angles"][1]
        angle["hook"] = "Buyer reality asks whether a contractor customer will pay for proof"
        angle["script"] = "Ask the contractor buyer to pay or reply before you validate proof demand."
    elif signal == "action":
        angle = value["angles"][1]
        angle["hook"] = "Buyer reality reveals a contractor proof budget and urgent decision"
        angle["script"] = "The contractor buyer has an urgent painful proof problem and budget risk."
    else:
        raise AssertionError(f"unsupported test signal: {signal}")
    return value, angle["angle_id"]


def _compact_bundle_with_verdict_grounding_failure(mode: str):
    value = _compact_bundle()
    if mode == "missing_verdict":
        angle = value["angles"][3]
        angle.update({
            "hook": "The opportunity targets a narrow buyer use case with painful constraints",
            "script": "A buyer has urgent pain. Validate this narrow use case and decide next.",
            "caption": "A buyer pain gets a narrow use case validation action.",
            "thumbnail_text": "NARROW BUYER TEST",
        })
    elif mode == "generic_claim":
        angle = value["angles"][0]
        angle["script"] += " This is guaranteed to work."
    elif mode == "external_fact":
        angle = value["angles"][0]
        angle["script"] += " Research shows 93% demand."
    elif mode == "contrarian_angle":
        angle = value["angles"][3]
        angle.update({
            "hook": "The opportunity gives contractor buyers painful proof constraints to validate",
            "script": "A contractor buyer has urgent proof pain. Validate the constraint and decide next.",
            "caption": "Contractor proof pain gives the buyer a validation decision.",
            "thumbnail_text": "CONTRACTOR PROOF BET",
        })
    elif mode == "builder_action":
        angle = value["angles"][4]
        angle.update({
            "hook": "First, contractor buyers face urgent proof pain and budget risk",
            "script": "The contractor buyer has urgent proof pain and a budget problem.",
            "caption": "Contractor proof pain leaves the buyer with a budget decision.",
            "thumbnail_text": "CONTRACTOR PROOF DECISION",
        })
    else:
        raise AssertionError(f"unsupported grounding test mode: {mode}")
    return value, angle["angle_id"]


def test_grounding_packet_is_compact_verdict_derived_and_safely_counted():
    verdict = json.loads(FIXTURE.read_text(encoding="utf-8"))["verdict"]
    packet = build_verdict_grounding_packet(verdict)
    diagnostics = grounding_packet_diagnostics(packet)
    verdict_text = json.dumps(verdict, ensure_ascii=False).casefold()

    assert packet["idea_label"] is None
    assert packet["idea_summary"] is None
    assert packet["verdict_label"] == verdict["verdict_headline"]
    assert packet["verdict_summary"] == verdict["top_reason"]
    for field in (
        "target_buyer_terms", "problem_terms", "pain_terms", "risk_terms",
        "validation_action_terms", "opportunity_terms", "verdict_signal_terms",
    ):
        assert packet[field]
        assert all(term in verdict_text for term in packet[field])
    assert packet["forbidden_external_fact_categories"] == list(EXTERNAL_FACT_CATEGORIES)
    assert diagnostics["grounding_packet_present"] is True
    assert diagnostics["grounding_packet_field_count"] == len(packet)
    assert diagnostics["grounding_packet_missing_fields"] == ["idea_label", "idea_summary"]
    assert diagnostics["grounding_terms_count"] > 0
    assert diagnostics["target_buyer_terms_count"] == len(packet["target_buyer_terms"])
    assert diagnostics["pain_terms_count"] == len(packet["pain_terms"])
    assert diagnostics["validation_action_terms_count"] == len(packet["validation_action_terms"])
    assert verdict["top_reason"] not in json.dumps(diagnostics, ensure_ascii=False)
    assert all(
        value is None or not isinstance(value, str) or len(value) <= 240
        for value in packet.values()
    )


@pytest.mark.parametrize(
    "claim, expected_category",
    [
        ("The market size is a billion-dollar opportunity.", "unsupported_market_claim"),
        ("Fortune 500 teams are the ideal customers.", "unsupported_buyer_claim"),
        ("The conversion rate will reach 40%.", "unsupported_metric_claim"),
        ("This will produce $50000 in revenue.", "unsupported_revenue_claim"),
        ("Launch this through TikTok immediately.", "unsupported_platform_claim"),
        ("Demand will be proven within 30 days.", "unsupported_timing_claim"),
        ("Unlike Acme, this competitor cannot respond.", "unsupported_competitor_claim"),
        ("This idea is guaranteed to work.", "unsupported_guarantee_claim"),
        ("This already has proven demand.", "unsupported_outcome_claim"),
        ("Acme Corp will become the buyer.", "unknown_entity_signal"),
    ],
)
def test_external_fact_classifier_returns_allowlisted_categories_only(claim, expected_category):
    verdict = json.loads(FIXTURE.read_text(encoding="utf-8"))["verdict"]
    packet = build_verdict_grounding_packet(verdict)

    categories = classify_external_fact_signals(claim, packet)

    assert expected_category in categories
    assert set(categories).issubset(EXTERNAL_FACT_CATEGORIES)


def test_external_fact_classifier_allows_verdict_and_required_project_terms():
    verdict = json.loads(FIXTURE.read_text(encoding="utf-8"))["verdict"]
    packet = build_verdict_grounding_packet(verdict)
    supported = (
        "The LIT verdict says contractor owners may refuse another standalone tool. "
        "A builder can run a Ghost Town Test validation test for the buyer, market, idea, risk, demand signal, and MVP. "
        "Visit GhostTownTest.com."
    )

    assert classify_external_fact_signals(supported, packet) == []


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


class CapturingFakeAdapter(FakeLLMAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prompts = []

    def generate_json(self, prompt, schema, model_profile):
        self.prompts.append(json.loads(prompt))
        return super().generate_json(prompt, schema, model_profile)


def test_fake_adapter_generates_valid_online_creative_pack_without_network(tmp_path):
    profile = LLMModelRegistry(local_path=NO_LOCAL_MODELS).require("fake-json-model", require_json_schema=True)
    adapter = CapturingFakeAdapter()
    provider = OnlineLLMCreativeGenerationProvider(profile, adapter)
    output, _, receipt = _generate(tmp_path, provider, online_explicit=True)
    pack, jobs, longform = _artifacts(output, receipt)
    assert receipt.status == "passed"
    assert receipt.provider_type == "online_llm"
    assert receipt.model_id == "fake-json-model"
    assert receipt.model_provider == "fake"
    assert receipt.model_profile_hash == profile.profile_hash
    assert receipt.adapter_type == "fake"
    assert receipt.network_called is False
    assert receipt.raw_response_stored is False
    assert receipt.schema_valid is True
    assert receipt.youtube_api_called is False
    assert receipt.videos_insert_called is False
    assert receipt.publish_attempted is False
    assert receipt.redacted_error is None
    assert receipt.estimated_input_tokens > 0
    assert receipt.estimated_output_tokens > 0
    assert receipt.estimated_cost == 0
    assert len(pack.angles) == len(jobs) == len(longform.ordered_chapters) == 5
    assert len(adapter.prompts) == 1
    assert adapter.prompts[0]["task"] == "generate_creative_bundle"
    prompt_input = adapter.prompts[0]["input"]
    assert set(prompt_input) == {
        "lit_verdict_id", "lit_verdict", "required_angles", "brand_context", "requirements",
    }
    assert "source_receipt_references" not in json.dumps(prompt_input)


def test_valid_fake_openrouter_response_creates_exactly_five_safe_short_jobs(tmp_path, monkeypatch):
    profile = LLMModelRegistry(local_path=NO_LOCAL_MODELS).require(
        "openrouter-free-router", require_json_schema=True,
    )
    compact = _compact_bundle()
    exposed_marker = "reasoning-must-not-be-stored"
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-openrouter-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    calls = []

    def transport(**request):
        calls.append(request)
        return {
            "choices": [{
                "message": {
                    "content": json.dumps(compact),
                    "reasoning_details": [{"text": exposed_marker}],
                },
            }],
            "model": "google/gemma-4-26b-a4b-it:free",
            "provider": "openrouter",
        }

    adapter = build_llm_adapter(
        profile,
        allow_network=True,
        require_config=True,
        transport=transport,
    )
    provider = OnlineLLMCreativeGenerationProvider(profile, adapter)
    output, generator, receipt = _generate(tmp_path, provider, online_explicit=True)
    pack, jobs, _ = _artifacts(output, receipt)
    persisted = generator.receipt_path(receipt.angle_pack_id).read_text(encoding="utf-8")

    assert receipt.status == "passed"
    assert receipt.model_provider == "openrouter"
    assert receipt.short_jobs_created == 5
    assert len(jobs) == 5
    assert pack.idea_summary == compact["idea_summary"]
    assert pack.verdict_summary == compact["verdict_summary"]
    assert {job.angle_id for job in jobs} == EXPECTED_ANGLES
    assert receipt.raw_response_stored is False
    assert receipt.reasoning_details_stored is False
    assert receipt.stream_enabled is False
    diagnostics = receipt.provider_diagnostics
    assert diagnostics["provider_selected_model"] == "google/gemma-4-26b-a4b-it:free"
    assert diagnostics["provider_selected_provider"] == "openrouter"
    assert diagnostics["content_present"] is True
    assert diagnostics["content_length"] > 0
    assert diagnostics["content_starts_with_json"] is True
    assert diagnostics["content_starts_with_markdown_fence"] is False
    assert diagnostics["json_extraction_used"] is False
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert diagnostics["schema_error_count"] == 0
    assert diagnostics["grounding_packet_present"] is True
    assert diagnostics["grounding_packet_field_count"] == 12
    assert diagnostics["grounding_packet_missing_fields"] == ["idea_label", "idea_summary"]
    assert diagnostics["grounding_terms_count"] > 0
    assert diagnostics["target_buyer_terms_count"] > 0
    assert diagnostics["pain_terms_count"] > 0
    assert diagnostics["risk_terms_count"] > 0
    assert diagnostics["validation_action_terms_count"] > 0
    assert diagnostics["verdict_signal_terms_count"] > 0
    assert diagnostics["opportunity_terms_count"] > 0
    assert diagnostics["external_fact_error_type"] is None
    assert diagnostics["external_fact_failed_angle_ids"] == []
    assert profile.max_output_tokens == 4000
    assert diagnostics["output_budget_tokens"] == 3500
    assert diagnostics["compact_prompt_budget_enabled"] is True
    assert diagnostics["expected_budget_profile"] == "compact_json_v1"
    assert diagnostics["truncation_risk_detected"] is False
    assert receipt.secrets_recorded is False
    assert receipt.publish_attempted is False
    assert receipt.youtube_api_called is False
    assert len(calls) == 1
    assert calls[0]["json"]["stream"] is False
    compact_prompt = calls[0]["json"]["messages"][1]["content"]
    for budget_rule in (
        "exactly 5 angles",
        "hook: max 120 characters",
        "script: max 450 characters",
        "caption: max 180 characters",
        "thumbnail_text: max 36 characters",
        "tags: max 4 items",
        "hashtags: max 4 items",
        "longform.title: max 90 characters",
        "longform.intro: max 250 characters",
        "longform chapter summary: max 160 characters",
        "transitions: max 3 items, max 80 characters each",
        "longform.conclusion: max 220 characters",
        "longform.description: max 300 characters",
        "Return compact JSON. Do not pretty-print. Do not add extra whitespace.",
        "Keep all fields concise. Complete the JSON object before ending.",
    ):
        assert budget_rule in compact_prompt
    assert "Return compact JSON only using the LLMCreativeBundleV1 schema." in compact_prompt
    assert "each hook must match its angle_id" in compact_prompt
    assert "each hook must include a concrete risk, buyer action, or validation mistake" in compact_prompt
    assert "thumbnail_text must be specific to the angle, not generic" in compact_prompt
    assert "every angle hook, script, caption, and thumbnail_text must include a concrete buyer/pain/action signal" in compact_prompt
    assert "buyer: name who has the problem or makes the decision" in compact_prompt
    assert "pain: name the costly mistake, delay, wasted build, missed demand, or invalid assumption" in compact_prompt
    assert "action: name what the builder should test, ask, validate, cut, or decide next" in compact_prompt
    assert "avoid generic startup language" in compact_prompt
    assert "No generic hooks." in compact_prompt
    assert "No generic builder advice." in compact_prompt
    assert "No external facts." in compact_prompt
    assert "Every hook must connect to the verdict." in compact_prompt
    assert "Every script must include buyer + pain + action." in compact_prompt
    assert "Every thumbnail must be specific to the angle and verdict." in compact_prompt
    assert "ghost_town_risk: name the risk of building for people who may not care" in compact_prompt
    assert "buyer_reality: confront whether a real buyer would pay, reply, book, switch, or act" in compact_prompt
    assert "fast_validation_test: name one fast test before building more and what result would prove interest" in compact_prompt
    assert "contrarian_opportunity: identify the narrow buyer/user/use case" in compact_prompt
    assert "builder_action_plan: state the next concrete builder action" in compact_prompt
    assert "Use only the grounding packet and the supplied LIT verdict." in compact_prompt
    assert "Do not add industries, platforms, metrics, examples, customer segments, revenue, competitors, geography, market size, timing claims, or external facts unless they appear in the LIT verdict." in compact_prompt
    assert "If a detail is missing, speak generally using buyer, market, validation test, builder action, idea, risk, or demand signal." in compact_prompt
    assert "Do not invent specifics." in compact_prompt
    assert "Grounding packet:" in compact_prompt
    assert all(angle_id in compact_prompt for angle_id in EXPECTED_ANGLES)
    assert "Run your idea through the Ghost Town Test at GhostTownTest.com" in compact_prompt
    assert "no external facts beyond the LIT verdict" in compact_prompt
    assert exposed_marker not in persisted
    assert "test-only-openrouter-key" not in persisted


def test_compact_bundle_normalizer_builds_internal_scaffolding_without_trusting_ids():
    from content_factory.autopilot.creative_providers import ANGLE_RUBRIC, CTA

    compact = LLMCreativeBundleV1.validate(_compact_bundle_missing_script_caption_cta())
    normalized = normalize_llm_creative_bundle(
        compact,
        angle_rubric=ANGLE_RUBRIC,
        canonical_cta="Configured fallback at GhostTownTest.com must not replace bundle CTA",
    )
    assert len(normalized["angles"]) == 5
    assert set(normalized["shorts"]) == EXPECTED_ANGLES
    bundle_cta = compact.value["cta"]
    assert all(value["cta"] == bundle_cta for value in normalized["shorts"].values())
    assert all(bundle_cta in value["script"] for value in normalized["shorts"].values())
    assert all(bundle_cta in value["caption"] for value in normalized["shorts"].values())
    assert all("GhostTownTest.com" in value["cta"] for value in normalized["shorts"].values())
    assert all(value["youtube_metadata_draft"]["cta"] == bundle_cta for value in normalized["shorts"].values())
    assert all(value["youtube_metadata_draft"]["live_publish_enabled"] is False for value in normalized["shorts"].values())
    assert normalized["longform"]["cta_to_ghosttowntest_com"] == bundle_cta
    assert len(normalized["longform"]["ordered_chapters"]) == 5
    assert len(normalized["longform"]["suggested_chapters_timestamps"]) == 6


@pytest.mark.parametrize(
    "mutation, expected_path",
    [
        (lambda value: value.pop("idea_summary"), "$.idea_summary"),
        (lambda value: value.pop("cta"), "$.cta"),
        (lambda value: value["angles"].pop(), "$.angles"),
        (lambda value: value["angles"].__setitem__(1, dict(value["angles"][0])), "$.angles[].angle_id"),
        (lambda value: value["angles"][0].__setitem__("angle_id", "unknown"), "$.angles[].angle_id"),
        (lambda value: value["angles"][0].pop("hook"), "$.angles[0].hook"),
        (lambda value: value.__setitem__("cta", "No website"), "$.cta"),
        (lambda value: value["angles"][0].__setitem__("tags", []), "$.angles[0].tags"),
        (lambda value: value["angles"][0].__setitem__("hashtags", []), "$.angles[0].hashtags"),
        (lambda value: value["longform"]["chapters"][0].__setitem__("angle_id", "unknown"), "$.longform.chapters[].angle_id"),
    ],
)
def test_compact_bundle_semantic_validation_blocks_invalid_shapes(mutation, expected_path):
    value = _compact_bundle()
    mutation(value)
    with pytest.raises(LLMBundleValidationError) as error:
        LLMCreativeBundleV1.validate(value)
    assert expected_path in error.value.paths


def _fallback_runner(tmp_path, adapter_factory):
    return CreativeFallbackRunner(
        registry=LLMModelRegistry(local_path=NO_LOCAL_MODELS),
        fallback_group_id="openrouter-free-creative-chain",
        output_root=tmp_path / "fallback output",
        adapter_factory=adapter_factory,
        now=lambda: NOW,
    )


def _openrouter_adapter_factory(response_for_profile):
    def factory(profile):
        def transport(**request):
            return response_for_profile(profile)

        return GenericHTTPAdapter(
            endpoint_url="https://openrouter.ai/api/v1",
            api_key="test-only-key",
            allow_network=True,
            endpoint_type="chat_json",
            transport=transport,
        )
    return factory


@pytest.mark.parametrize(
    "first_response, expected_error",
    [
        ({"choices": [{"message": {"content": "  "}}]}, "empty_provider_content"),
        ({}, "empty_provider_content"),
        ({"choices": [{"message": {"content": '{"broken":'}}]}, "malformed_json"),
        ({"choices": [{"message": {"content": json.dumps({"idea_summary": "missing fields"})}}]}, "compact_schema_invalid"),
    ],
)
def test_compact_openrouter_fallback_records_safe_failure_then_stops_on_normalized_pass(
    tmp_path, first_response, expected_error,
):
    valid_content = json.dumps(_compact_bundle())

    def response_for_profile(profile):
        if profile.model_id == "openrouter-gemma-4-26b-free":
            return first_response
        return {
            "choices": [{"message": {"content": valid_content}}],
            "model": profile.provider_model,
            "provider": "openrouter",
        }

    runner = _fallback_runner(tmp_path, _openrouter_adapter_factory(response_for_profile))
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)

    assert fallback["status"] == "passed"
    assert fallback["total_attempts"] == 2
    assert fallback["selected_model_id"] == "openrouter-gemma-4-31b-free"
    first_diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    if expected_error == "compact_schema_invalid":
        assert first_diagnostics["schema_error_type"] == expected_error
        assert first_diagnostics["parse_error_type"] is None
        assert first_diagnostics["parse_stage"] == "compact_schema"
        assert first_diagnostics["json_parse_error_type"] is None
    else:
        assert first_diagnostics["parse_error_type"] == expected_error
    if expected_error == "malformed_json":
        assert first_diagnostics["json_parse_error_type"] == "unexpected_end_of_json"
        assert first_diagnostics["likely_truncated"] is True
        assert first_diagnostics["truncation_risk_detected"] is True
        assert first_diagnostics["output_budget_tokens"] == 3500
        assert first_diagnostics["compact_prompt_budget_enabled"] is True
        assert first_diagnostics["expected_budget_profile"] == "compact_json_v1"
    assert first_diagnostics["internal_schema_valid"] is False
    selected_diagnostics = fallback["attempts"][1]["provider_diagnostics"]
    assert selected_diagnostics["compact_schema_valid"] is True
    assert selected_diagnostics["internal_schema_valid"] is True
    assert selected_diagnostics["schema_error_count"] == 0
    assert receipt is not None and generator is not None
    assert fallback_path.is_file()
    first_receipt_path = runner.output_root / fallback["attempts"][0]["receipt"]
    assert not first_receipt_path.parent.joinpath("creative_angle_pack.json").exists()
    first_receipt = json.loads(first_receipt_path.read_text(encoding="utf-8"))
    assert first_receipt["output_hash"] == "not_available"
    assert all(path.startswith("$") for path in first_diagnostics["missing_required_fields"])
    persisted = fallback_path.read_text(encoding="utf-8")
    assert valid_content not in persisted
    assert "test-only-key" not in persisted


def test_fenced_compact_openrouter_json_records_extraction_without_storing_content(tmp_path):
    compact_content = json.dumps(_compact_bundle())
    fenced = f"```json\n{compact_content}\n```"
    factory = _openrouter_adapter_factory(
        lambda profile: {"choices": [{"message": {"content": fenced}}]},
    )
    fallback, fallback_path, receipt, _ = _fallback_runner(tmp_path, factory).run(lit_verdict_file=FIXTURE)
    assert fallback["status"] == "passed"
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    assert diagnostics["content_starts_with_markdown_fence"] is True
    assert diagnostics["markdown_fence_detected"] is True
    assert diagnostics["json_extraction_used"] is True
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert receipt is not None
    assert compact_content not in fallback_path.read_text(encoding="utf-8")


def test_malformed_json_receipt_records_safe_parse_diagnostics_without_content(tmp_path):
    markers = (
        "private-script-marker-must-not-store",
        "private-caption-marker-must-not-store",
        "private-longform-marker-must-not-store",
    )
    malformed = (
        '{\n  "script": "' + markers[0] + '",\n'
        '  "caption": "' + markers[1] + '",\n'
        '  "longform": "' + markers[2] + '",\n}'
    )
    runner = _fallback_runner(
        tmp_path,
        _openrouter_adapter_factory(
            lambda profile: {"choices": [{"message": {"content": malformed}}]},
        ),
    )

    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    persisted = fallback_path.read_text(encoding="utf-8")

    assert fallback["status"] == "blocked"
    assert fallback["total_attempts"] == 5
    assert receipt is None and generator is None
    assert diagnostics["parse_error_type"] == "malformed_json"
    assert diagnostics["parse_stage"] == "json_loads"
    assert diagnostics["json_parse_error_type"] == "trailing_comma"
    assert diagnostics["json_parse_error_line"] == 5
    assert diagnostics["json_parse_error_column"] == 1
    assert isinstance(diagnostics["json_parse_error_position"], int)
    assert diagnostics["extracted_json_length"] == len(malformed)
    assert diagnostics["likely_truncated"] is False
    assert diagnostics["compact_schema_valid"] is False
    assert diagnostics["internal_schema_valid"] is False
    assert diagnostics["quality_valid"] is False
    assert '"content_snippet"' not in persisted
    assert '"raw_content"' not in persisted
    assert '"extracted_json"' not in persisted
    assert all(marker not in persisted for marker in markers)
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False


def test_compact_openrouter_fallback_continues_on_internal_normalization_failure(tmp_path, monkeypatch):
    import content_factory.autopilot.creative_providers as provider_module

    original_normalizer = provider_module.normalize_llm_creative_bundle

    def conditional_normalizer(bundle, **kwargs):
        if bundle.value["idea_summary"] == "trigger internal failure":
            raise ValueError("test-only internal failure")
        return original_normalizer(bundle, **kwargs)

    monkeypatch.setattr(provider_module, "normalize_llm_creative_bundle", conditional_normalizer)
    invalid = _compact_bundle()
    invalid["idea_summary"] = "trigger internal failure"
    valid = _compact_bundle()

    def response_for_profile(profile):
        content = invalid if profile.model_id == "openrouter-gemma-4-26b-free" else valid
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    fallback, _, receipt, _ = _fallback_runner(
        tmp_path, _openrouter_adapter_factory(response_for_profile),
    ).run(lit_verdict_file=FIXTURE)
    assert fallback["status"] == "passed"
    assert fallback["total_attempts"] == 2
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is False
    assert diagnostics["schema_error_type"] == "internal_schema_invalid"
    assert diagnostics["parse_error_type"] is None
    assert receipt is not None


def test_compact_openrouter_fallback_continues_on_normalized_quality_failure(tmp_path):
    markers = (
        "private-hook-marker-must-not-store",
        "private-script-marker-must-not-store",
        "private-caption-marker-must-not-store",
        "private-longform-marker-must-not-store",
    )
    invalid = _compact_bundle()
    invalid["angles"][0]["hook"] = f"Seven generic words avoid every expected angle signal {markers[0]}"
    invalid["angles"][0]["script"] += f" {markers[1]}"
    invalid["angles"][0]["caption"] += f" {markers[2]}"
    invalid["longform"]["intro"] += f" {markers[3]}"
    valid = _compact_bundle()

    def response_for_profile(profile):
        content = invalid if profile.model_id == "openrouter-gemma-4-26b-free" else valid
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    runner = _fallback_runner(
        tmp_path, _openrouter_adapter_factory(response_for_profile),
    )
    fallback, fallback_path, receipt, _ = runner.run(lit_verdict_file=FIXTURE)
    first_receipt_path = runner.output_root / fallback["attempts"][0]["receipt"]
    persisted = fallback_path.read_text(encoding="utf-8") + first_receipt_path.read_text(encoding="utf-8")
    assert fallback["status"] == "passed"
    assert fallback["total_attempts"] == 2
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert diagnostics["parse_error_type"] is None
    assert diagnostics["quality_error_type"] == "missing_hook_specificity"
    assert diagnostics["hook_specificity_error_type"] == "angle_mismatch_hook"
    assert diagnostics["hook_specificity_failed_angle_ids"] == ["ghost_town_risk"]
    assert diagnostics["quality_failed_checks"] == ["specific_hooks"]
    assert diagnostics["ghosttowntest_cta_present"] is True
    assert not any(path.endswith(".ghosttowntest_cta") for path in diagnostics["quality_missing_fields"])
    assert diagnostics["final_block_reason"] == "quality_invalid"
    assert fallback["attempts"][0]["stage_reached"] == "quality_invalid"
    assert fallback["best_attempt_stage_reached"] == "passed"
    assert all(marker not in json.dumps(diagnostics) for marker in markers)
    assert all(marker not in persisted for marker in markers)
    assert '"hook"' not in json.dumps(diagnostics)
    assert '"script"' not in json.dumps(diagnostics)
    assert '"caption"' not in json.dumps(diagnostics)
    assert '"longform"' not in json.dumps(diagnostics)
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert receipt is not None


@pytest.mark.parametrize(
    "missing_signal, expected_error_type, missing_count_field",
    [
        ("buyer", "missing_buyer_signal", "buyer_signal_missing_count"),
        ("pain", "missing_pain_signal", "pain_signal_missing_count"),
        ("action", "missing_action_signal", "action_signal_missing_count"),
    ],
)
def test_buyer_pain_action_failure_records_safe_signal_diagnostics(
    tmp_path, missing_signal, expected_error_type, missing_count_field,
):
    invalid, failed_angle_id = _compact_bundle_missing_buyer_pain_action_signal(missing_signal)
    runner = _fallback_runner(
        tmp_path,
        _openrouter_adapter_factory(
            lambda profile: {"choices": [{"message": {"content": json.dumps(invalid)}}]},
        ),
    )

    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    persisted = fallback_path.read_text(encoding="utf-8")
    diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
    failed_angle = next(angle for angle in invalid["angles"] if angle["angle_id"] == failed_angle_id)

    assert fallback["status"] == "blocked"
    assert fallback["total_attempts"] == 5
    assert fallback["final_block_reason"] == "quality_invalid"
    assert fallback["best_attempt_stage_reached"] == "quality_invalid"
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert diagnostics["cta_present"] is True
    assert diagnostics["ghosttowntest_cta_present"] is True
    assert diagnostics["quality_valid"] is False
    assert diagnostics["quality_failed_checks"] == ["buyer_pain_action_specificity"]
    assert diagnostics["quality_error_type"] == expected_error_type
    assert diagnostics["buyer_pain_action_error_type"] == expected_error_type
    assert diagnostics["buyer_pain_action_failed_angle_ids"] == [failed_angle_id]
    assert failed_angle_id not in diagnostics["buyer_pain_action_passed_angle_ids"]
    assert len(diagnostics["buyer_pain_action_passed_angle_ids"]) == 4
    assert diagnostics[missing_count_field] == 1
    assert diagnostics["buyer_pain_action_error_count"] == 1
    assert failed_angle["hook"] not in diagnostics_json
    assert failed_angle["script"] not in diagnostics_json
    assert '"hook"' not in diagnostics_json
    assert '"script"' not in diagnostics_json
    assert '"caption"' not in diagnostics_json
    assert '"thumbnail_text"' not in diagnostics_json
    assert '"longform"' not in diagnostics_json
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert all(str(value) not in persisted for value in (failed_angle["hook"], failed_angle["script"]))
    assert receipt is None and generator is None


@pytest.mark.parametrize(
    "mode, expected_error_type, count_field",
    [
        ("missing_verdict", "missing_verdict_grounding", "verdict_signal_missing_count"),
        ("generic_claim", "generic_claim_signal", "generic_claim_signal_count"),
        ("external_fact", "external_fact_signal", "external_fact_signal_count"),
        ("contrarian_angle", "missing_angle_specificity", "angle_specificity_missing_count"),
        ("builder_action", "missing_angle_specificity", "angle_specificity_missing_count"),
    ],
)
def test_verdict_grounding_failure_records_safe_angle_diagnostics(
    tmp_path, mode, expected_error_type, count_field,
):
    invalid, failed_angle_id = _compact_bundle_with_verdict_grounding_failure(mode)
    runner = _fallback_runner(
        tmp_path,
        _openrouter_adapter_factory(
            lambda profile: {"choices": [{"message": {"content": json.dumps(invalid)}}]},
        ),
    )

    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
    persisted = fallback_path.read_text(encoding="utf-8")
    failed_angle = next(angle for angle in invalid["angles"] if angle["angle_id"] == failed_angle_id)

    assert fallback["status"] == "blocked"
    assert fallback["final_block_reason"] == "quality_invalid"
    assert fallback["best_attempt_stage_reached"] == "quality_invalid"
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert diagnostics["cta_present"] is True
    assert diagnostics["ghosttowntest_cta_present"] is True
    assert diagnostics["quality_valid"] is False
    assert "verdict_grounded_claims" in diagnostics["quality_failed_checks"]
    assert diagnostics["quality_error_type"] == "missing_verdict_grounding"
    assert diagnostics["verdict_grounding_error_type"] == expected_error_type
    assert diagnostics["verdict_grounding_failed_angle_ids"] == [failed_angle_id]
    assert failed_angle_id not in diagnostics["verdict_grounding_passed_angle_ids"]
    assert len(diagnostics["verdict_grounding_passed_angle_ids"]) == 4
    assert diagnostics[count_field] == 1
    if mode in {"generic_claim", "external_fact"}:
        expected_category = (
            "unsupported_guarantee_claim"
            if mode == "generic_claim"
            else "unsupported_metric_claim"
        )
        assert diagnostics["external_fact_error_type"] == expected_category
        assert diagnostics["external_fact_failed_angle_ids"] == [failed_angle_id]
        assert diagnostics["external_fact_signal_categories"] == [expected_category]
        assert diagnostics["external_fact_category_counts"] == {expected_category: 1}
    else:
        assert diagnostics["external_fact_error_type"] is None
        assert diagnostics["external_fact_failed_angle_ids"] == []
    assert failed_angle["hook"] not in diagnostics_json
    assert failed_angle["script"] not in diagnostics_json
    assert failed_angle["caption"] not in diagnostics_json
    assert failed_angle["thumbnail_text"] not in diagnostics_json
    assert '"hook"' not in diagnostics_json
    assert '"script"' not in diagnostics_json
    assert '"caption"' not in diagnostics_json
    assert '"thumbnail_text"' not in diagnostics_json
    assert '"longform"' not in diagnostics_json
    assert all(
        failed_angle[field] not in persisted
        for field in ("hook", "script", "caption", "thumbnail_text")
    )
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert receipt is None and generator is None


def test_hook_specificity_diagnostics_do_not_store_hook_text(tmp_path):
    invalid = _compact_bundle()
    private_hook = "The opportunity gives every buyer a painful action before launch"
    invalid["angles"][3]["hook"] = private_hook
    runner = _fallback_runner(
        tmp_path,
        _openrouter_adapter_factory(
            lambda profile: {"choices": [{"message": {"content": json.dumps(invalid)}}]},
        ),
    )

    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)

    assert fallback["status"] == "blocked"
    assert diagnostics["quality_failed_checks"] == ["specific_hooks"]
    assert diagnostics["quality_error_type"] == "missing_hook_specificity"
    assert diagnostics["hook_specificity_error_type"] == "missing_verdict_signal"
    assert diagnostics["hook_specificity_failed_angle_ids"] == ["contrarian_opportunity"]
    assert diagnostics["hook_specificity_passed_angle_ids"] == [
        "ghost_town_risk",
        "buyer_reality",
        "fast_validation_test",
        "builder_action_plan",
    ]
    assert diagnostics["verdict_signal_missing_hook_count"] == 1
    assert diagnostics["generic_hook_count"] == 0
    assert diagnostics["angle_mismatch_hook_count"] == 0
    assert private_hook not in diagnostics_json
    assert private_hook not in fallback_path.read_text(encoding="utf-8")
    assert '"hook"' not in diagnostics_json
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert receipt is None and generator is None


def test_canonical_cta_propagation_clears_safe_quality_diagnostics(tmp_path):
    marker = "quality-diagnostic-marker-must-not-store"
    invalid = _compact_bundle_missing_script_caption_cta(marker)

    runner = _fallback_runner(
        tmp_path,
        _openrouter_adapter_factory(
            lambda profile: {"choices": [{"message": {"content": json.dumps(invalid)}}]},
        ),
    )
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    diagnostics = fallback["attempts"][0]["provider_diagnostics"]
    first_receipt = json.loads((runner.output_root / fallback["attempts"][0]["receipt"]).read_text(encoding="utf-8"))
    persisted = fallback_path.read_text(encoding="utf-8") + json.dumps(first_receipt, ensure_ascii=False)

    assert fallback["status"] == "passed"
    assert fallback["total_attempts"] == 1
    assert receipt is not None and generator is not None
    assert fallback["attempts"][0]["schema_valid"] is True
    assert fallback["attempts"][0]["quality_valid"] is True
    assert fallback["attempts"][0]["stage_reached"] == "passed"
    assert diagnostics["parse_error_type"] is None
    assert diagnostics["schema_error_type"] is None
    assert diagnostics["compact_schema_valid"] is True
    assert diagnostics["internal_schema_valid"] is True
    assert diagnostics["quality_valid"] is True
    assert diagnostics["quality_error_type"] is None
    assert diagnostics["quality_error_count"] == 0
    assert diagnostics["quality_failed_checks"] == []
    assert diagnostics["required_angle_ids_present"] == [
        "ghost_town_risk",
        "buyer_reality",
        "fast_validation_test",
        "contrarian_opportunity",
        "builder_action_plan",
    ]
    assert diagnostics["required_angle_ids_missing"] == []
    assert diagnostics["cta_present"] is True
    assert diagnostics["ghosttowntest_cta_present"] is True
    assert diagnostics["longform_present"] is True
    assert diagnostics["scripts_present_count"] == 5
    assert diagnostics["captions_present_count"] == 5
    assert diagnostics["thumbnail_text_present_count"] == 5
    assert diagnostics["hashtags_present_count"] == 5
    assert not any(path.endswith(".ghosttowntest_cta") for path in diagnostics["quality_missing_fields"])
    assert marker not in persisted
    assert marker not in json.dumps(diagnostics)
    assert first_receipt["raw_response_stored"] is False
    assert first_receipt["reasoning_details_stored"] is False
    assert first_receipt["publish_attempted"] is False
    assert first_receipt["youtube_api_called"] is False
    assert first_receipt["videos_insert_called"] is False
    assert first_receipt["safety"]["full_autopilot_enabled"] is False


def test_fallback_best_attempt_stage_prefers_quality_invalid_over_parse_and_rate_limit(tmp_path):
    marker = "best-stage-marker-must-not-store"
    two_failures, _ = _compact_bundle_missing_buyer_pain_action_signal("buyer")
    two_failures["angles"][0]["hook"] = (
        f"Seven generic words avoid every expected angle signal {marker}"
    )
    one_failure, _ = _compact_bundle_missing_buyer_pain_action_signal("action")

    class RateLimitedResponse:
        status_code = 429

        def raise_for_status(self):
            raise RuntimeError("provider details must not be stored")

    def response_for_profile(profile):
        if profile.model_id == "openrouter-gemma-4-26b-free":
            return {"choices": [{"message": {"content": '{"broken":'}}]}
        if profile.model_id == "openrouter-gemma-4-31b-free":
            return {"choices": [{"message": {"content": json.dumps(two_failures)}}]}
        if profile.model_id == "openrouter-llama-3-3-70b-free":
            return RateLimitedResponse()
        if profile.model_id == "openrouter-gpt-oss-120b-free":
            return {"choices": [{"message": {"content": json.dumps(one_failure)}}]}
        return {
            "choices": [{"message": {"content": json.dumps({"idea_summary": "missing fields"})}}],
        }

    runner = _fallback_runner(tmp_path, _openrouter_adapter_factory(response_for_profile))
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    second = fallback["attempts"][1]
    fourth = fallback["attempts"][3]
    fourth_diagnostics = fourth["provider_diagnostics"]

    assert fallback["status"] == "blocked"
    assert fallback["final_block_reason"] == "quality_invalid"
    assert fallback["best_attempt_number"] == 4
    assert fallback["best_attempt_model_id"] == "openrouter-gpt-oss-120b-free"
    assert fallback["best_attempt_provider_model"] == "openai/gpt-oss-120b:free"
    assert fallback["best_attempt_stage_reached"] == "quality_invalid"
    assert [attempt["stage_reached"] for attempt in fallback["attempts"]] == [
        "malformed_json",
        "quality_invalid",
        "provider_rate_limited",
        "quality_invalid",
        "compact_schema_invalid",
    ]
    assert fallback["attempts"][0]["provider_diagnostics"]["parse_error_type"] == "malformed_json"
    assert fallback["attempts"][2]["provider_diagnostics"]["provider_error_type"] == "rate_limited"
    assert fallback["attempts"][2]["provider_diagnostics"]["parse_error_type"] is None
    assert second["provider_diagnostics"]["quality_error_count"] == 2
    assert second["provider_diagnostics"]["quality_failed_checks"] == [
        "specific_hooks",
        "buyer_pain_action_specificity",
    ]
    assert fourth["schema_valid"] is True
    assert fourth["quality_valid"] is False
    assert fourth_diagnostics["quality_error_count"] == 1
    assert fourth_diagnostics["compact_schema_valid"] is True
    assert fourth_diagnostics["internal_schema_valid"] is True
    assert fourth_diagnostics["parse_error_type"] is None
    assert fourth_diagnostics["quality_error_type"] == "missing_action_signal"
    assert fourth_diagnostics["quality_failed_checks"] == ["buyer_pain_action_specificity"]
    assert fourth_diagnostics["buyer_pain_action_error_type"] == "missing_action_signal"
    assert fourth_diagnostics["ghosttowntest_cta_present"] is True
    assert not any(
        path.endswith(".ghosttowntest_cta")
        for path in fourth_diagnostics["quality_missing_fields"]
    )
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["videos_insert_called"] is False
    assert marker not in fallback_path.read_text(encoding="utf-8")
    assert receipt is None and generator is None


def test_best_attempt_tie_break_prefers_fewer_failed_checks_after_error_count():
    attempts = [
        {
            "attempt_number": 1,
            "stage_reached": "quality_invalid",
            "provider_diagnostics": {
                "quality_error_count": 1,
                "quality_failed_checks": ["specific_hooks", "thumbnail_specificity"],
            },
        },
        {
            "attempt_number": 2,
            "stage_reached": "quality_invalid",
            "provider_diagnostics": {
                "quality_error_count": 1,
                "quality_failed_checks": ["buyer_pain_action_specificity"],
            },
        },
    ]

    assert CreativeFallbackRunner._best_attempt(attempts)["attempt_number"] == 2


@pytest.mark.parametrize("first_mode", ["malformed_json", "schema_invalid"])
def test_openrouter_fallback_retries_invalid_json_then_stops_on_first_valid_model(tmp_path, first_mode):
    adapters = {}

    def adapter_factory(profile):
        mode = first_mode if profile.model_id == "openrouter-gemma-4-26b-free" else "valid"
        adapter = FakeLLMAdapter(response_mode=mode)
        adapters[profile.model_id] = adapter
        return adapter

    runner = _fallback_runner(tmp_path, adapter_factory)
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)

    assert fallback["status"] == "passed"
    assert fallback["selected_model_id"] == "openrouter-gemma-4-31b-free"
    assert fallback["selected_provider_model"] == "google/gemma-4-31b-it:free"
    assert fallback["total_attempts"] == 2
    assert [row["status"] for row in fallback["attempts"]] == ["blocked", "passed"]
    assert fallback["network_called"] is False
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["stream_enabled"] is False
    assert receipt is not None and generator is not None
    assert receipt.source_receipt_references["fallback_attempt_receipt"] == (
        fallback_path.relative_to(runner.output_root).as_posix()
    )
    assert generator.receipt_path(receipt.angle_pack_id).is_file()
    assert not adapters["openrouter-gemma-4-31b-free"].network_called


class QualityInvalidFakeAdapter(FakeLLMAdapter):
    def generate_json(self, prompt, schema, model_profile):
        value = super().generate_json(prompt, schema, model_profile)
        value["shorts"]["ghost_town_risk"]["hook"] = (
            "Seven generic words avoid every expected angle signal"
        )
        return value


def test_openrouter_fallback_retries_quality_invalid_pack(tmp_path):
    def adapter_factory(profile):
        if profile.model_id == "openrouter-gemma-4-26b-free":
            return QualityInvalidFakeAdapter()
        return FakeLLMAdapter()

    fallback, _, receipt, _ = _fallback_runner(tmp_path, adapter_factory).run(lit_verdict_file=FIXTURE)
    assert fallback["status"] == "passed"
    assert fallback["total_attempts"] == 2
    assert fallback["attempts"][0]["schema_valid"] is True
    assert fallback["attempts"][0]["quality_valid"] is False
    assert receipt is not None and receipt.model_id == "openrouter-gemma-4-31b-free"


def test_openrouter_fallback_all_failures_write_blocked_redacted_attempt_receipts(tmp_path):
    runner = _fallback_runner(tmp_path, lambda profile: FakeLLMAdapter(response_mode="malformed_json"))
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    persisted = fallback_path.read_text(encoding="utf-8")

    assert fallback["status"] == "blocked"
    assert fallback["total_attempts"] == 5
    assert receipt is None and generator is None
    assert all(row["status"] == "blocked" for row in fallback["attempts"])
    assert all((runner.output_root / row["receipt"]).is_file() for row in fallback["attempts"])
    assert "api_key" not in persisted.casefold()
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["videos_insert_called"] is False
    assert fallback["secrets_recorded"] is False
    assert fallback["raw_response_stored"] is False


def test_openrouter_fallback_stops_on_secret_detection(tmp_path):
    def adapter_factory(profile):
        if profile.model_id == "openrouter-gemma-4-26b-free":
            return SecretFakeAdapter()
        return FakeLLMAdapter()

    fallback, _, receipt, _ = _fallback_runner(tmp_path, adapter_factory).run(lit_verdict_file=FIXTURE)
    assert fallback["status"] == "blocked"
    assert fallback["total_attempts"] == 1
    assert fallback["attempts"][0]["status"] == "blocked"
    assert receipt is None


def test_openrouter_fallback_missing_credentials_fails_closed_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-openrouter-key-must-not-store")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    runner = CreativeFallbackRunner(
        registry=LLMModelRegistry(local_path=NO_LOCAL_MODELS),
        fallback_group_id="openrouter-free-creative-chain",
        output_root=tmp_path / "fallback output",
        now=lambda: NOW,
    )
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    persisted = fallback_path.read_text(encoding="utf-8")

    assert fallback["status"] == "blocked"
    assert fallback["final_block_reason"] == "configuration_error"
    assert fallback["total_attempts"] == 0
    assert fallback["configuration_error"]
    assert fallback["configuration_error_type"] == "missing_environment_variables"
    assert fallback["configuration_error_stage"] == "environment_validation"
    assert fallback["missing_environment_variable_names"] == ["OPENROUTER_BASE_URL"]
    assert fallback["fallback_group_found"] is True
    assert fallback["fallback_profile_count"] == 5
    assert fallback["provider_profile_ids"] == [
        "openrouter-gemma-4-26b-free",
        "openrouter-gemma-4-31b-free",
        "openrouter-llama-3-3-70b-free",
        "openrouter-gpt-oss-120b-free",
        "openrouter-free-router",
    ]
    assert fallback["online_provider_selected"] is True
    assert fallback["remote_provider_allowed"] is True
    assert fallback["local_provider_required"] is False
    assert fallback["attempted_before_config_error"] is False
    assert fallback["network_called"] is False
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["videos_insert_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert fallback["supervised_autopilot_enabled"] is False
    assert fallback["live_publishing_enabled"] is False
    assert "test-only-openrouter-key-must-not-store" not in persisted
    assert "Authorization" not in persisted
    assert fallback_path.is_file()
    assert receipt is None and generator is None
    assert calls == []


def test_fallback_group_missing_is_diagnosed_safely_before_attempts(tmp_path):
    runner = CreativeFallbackRunner(
        registry=LLMModelRegistry(local_path=NO_LOCAL_MODELS),
        fallback_group_id="missing-openrouter-chain",
        output_root=tmp_path / "fallback output",
        now=lambda: NOW,
    )
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    persisted = fallback_path.read_text(encoding="utf-8")

    assert fallback["status"] == "blocked"
    assert fallback["final_block_reason"] == "configuration_error"
    assert fallback["total_attempts"] == 0
    assert fallback["configuration_error_type"] == "fallback_group_not_found"
    assert fallback["configuration_error_stage"] == "fallback_group_lookup"
    assert fallback["missing_environment_variable_names"] == []
    assert fallback["fallback_group_found"] is False
    assert fallback["fallback_profile_count"] == 0
    assert fallback["provider_profile_ids"] == []
    assert fallback["attempted_before_config_error"] is False
    assert fallback["network_called"] is False
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert "api_key" not in persisted.casefold()
    assert receipt is None and generator is None


def test_fallback_group_found_but_empty_is_diagnosed_safely(tmp_path):
    class EmptyGroupRegistry:
        def get_fallback_group(self, fallback_group_id):
            return SimpleNamespace(fallback_group_id=fallback_group_id, model_ids=())

        def require(self, model_id, *, require_json_schema=True):
            raise AssertionError("empty fallback group must not require profiles")

    runner = CreativeFallbackRunner(
        registry=EmptyGroupRegistry(),
        fallback_group_id="empty-openrouter-chain",
        output_root=tmp_path / "fallback output",
        now=lambda: NOW,
    )
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)

    assert fallback["status"] == "blocked"
    assert fallback["final_block_reason"] == "configuration_error"
    assert fallback["total_attempts"] == 0
    assert fallback["configuration_error_type"] == "fallback_group_empty"
    assert fallback["configuration_error_stage"] == "fallback_group_lookup"
    assert fallback["fallback_group_found"] is True
    assert fallback["fallback_profile_count"] == 0
    assert fallback["provider_profile_ids"] == []
    assert fallback["missing_environment_variable_names"] == []
    assert fallback["attempted_before_config_error"] is False
    assert fallback["network_called"] is False
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert fallback_path.is_file()
    assert receipt is None and generator is None


def test_valid_openrouter_config_proceeds_to_attempts_without_local_only_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-openrouter-key-must-not-store")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    calls = []

    class MalformedResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"broken":'}}]}

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return MalformedResponse()

    monkeypatch.setattr("requests.post", fake_post)
    runner = CreativeFallbackRunner(
        registry=LLMModelRegistry(local_path=NO_LOCAL_MODELS),
        fallback_group_id="openrouter-free-creative-chain",
        output_root=tmp_path / "fallback output",
        now=lambda: NOW,
    )
    fallback, fallback_path, receipt, generator = runner.run(lit_verdict_file=FIXTURE)
    persisted = fallback_path.read_text(encoding="utf-8")

    assert fallback["status"] == "blocked"
    assert fallback["total_attempts"] == 5
    assert fallback["configuration_error"] is None
    assert fallback["configuration_error_type"] is None
    assert fallback["configuration_error_stage"] is None
    assert fallback["missing_environment_variable_names"] == []
    assert fallback["fallback_group_found"] is True
    assert fallback["fallback_profile_count"] == 5
    assert fallback["remote_provider_allowed"] is True
    assert fallback["local_provider_required"] is False
    assert fallback["attempted_before_config_error"] is False
    assert fallback["attempts"][0]["stage_reached"] == "malformed_json"
    assert fallback["attempts"][0]["network_called"] is True
    assert len(calls) == 5
    assert all(call[1]["json"]["stream"] is False for call in calls)
    assert "test-only-openrouter-key-must-not-store" not in persisted
    assert "Authorization" not in persisted
    assert fallback["raw_response_stored"] is False
    assert fallback["reasoning_details_stored"] is False
    assert fallback["publish_attempted"] is False
    assert fallback["youtube_api_called"] is False
    assert fallback["videos_insert_called"] is False
    assert fallback["full_autopilot_enabled"] is False
    assert receipt is None and generator is None


def test_model_and_fallback_group_cli_options_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "generate", "--lit-verdict-file", str(FIXTURE), "--provider", "online_llm",
            "--model", "fake-json-model", "--fallback-group", "openrouter-free-creative-chain",
        ])


def test_fallback_group_requires_online_provider(tmp_path, capsys):
    result = main([
        "generate", "--lit-verdict-file", str(FIXTURE), "--provider", "deterministic",
        "--fallback-group", "openrouter-free-creative-chain", "--output-root", str(tmp_path),
    ])
    assert result == 1
    assert "requires --provider online_llm" in capsys.readouterr().err


@pytest.mark.parametrize("response_mode", ["malformed_json", "schema_invalid"])
def test_invalid_fake_llm_output_writes_blocked_receipt_only(tmp_path, response_mode):
    profile = LLMModelRegistry(local_path=NO_LOCAL_MODELS).require("fake-json-model", require_json_schema=True)
    provider = OnlineLLMCreativeGenerationProvider(
        profile, FakeLLMAdapter(response_mode=response_mode),
    )
    _, generator, receipt = _generate(tmp_path, provider, online_explicit=True)
    assert receipt.status == "blocked"
    assert receipt.artifacts == {}
    assert receipt.short_jobs_created == 0
    assert receipt.network_called is False
    assert receipt.raw_response_stored is False
    assert list(generator.pack_dir(receipt.angle_pack_id).iterdir()) == [
        generator.receipt_path(receipt.angle_pack_id)
    ]


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


class SecretFakeAdapter(FakeLLMAdapter):
    def generate_json(self, prompt, schema, model_profile):
        value = super().generate_json(prompt, schema, model_profile)
        value["shorts"]["ghost_town_risk"]["caption"] += " api_key=online-secret-never-store"
        return value


def test_online_provider_output_containing_secret_is_blocked_and_redacted(tmp_path):
    profile = LLMModelRegistry(local_path=NO_LOCAL_MODELS).require("fake-json-model", require_json_schema=True)
    provider = OnlineLLMCreativeGenerationProvider(profile, SecretFakeAdapter())
    _, generator, receipt = _generate(tmp_path, provider, online_explicit=True)
    persisted = generator.receipt_path(receipt.angle_pack_id).read_text(encoding="utf-8")
    assert receipt.status == "blocked"
    assert receipt.schema_valid is True
    assert receipt.artifacts == {}
    assert "online-secret-never-store" not in persisted


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
    assert receipt.youtube_api_called is False
    assert receipt.videos_insert_called is False
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


def test_deterministic_cli_does_not_load_model_registry_or_credentials(tmp_path, monkeypatch):
    def refuse_registry(*args, **kwargs):
        raise AssertionError("deterministic mode must not load the LLM registry")

    monkeypatch.setattr(
        "content_factory.autopilot.creative_angle_pack.LLMModelRegistry",
        refuse_registry,
    )
    assert main([
        "generate",
        "--lit-verdict-file", str(FIXTURE),
        "--provider", "deterministic",
        "--output-root", str(tmp_path / "output"),
    ]) == 0


def test_online_generic_model_refuses_missing_credentials_without_network(tmp_path, monkeypatch, capsys):
    example = json.loads(Path("config/examples/llm_models.example.json").read_text(encoding="utf-8"))
    profile = dict(next(row for row in example["models"] if row["model_id"] == "generic-http-example"))
    profile.update({"model_id": "enabled-generic-test", "enabled": True})
    models_file = tmp_path / "models.json"
    models_file.write_text(json.dumps({"models": [profile]}), encoding="utf-8")
    for name in (
        "LLM_EXAMPLE_PROVIDER_API_URL", "LLM_EXAMPLE_PROVIDER_API_KEY",
        "CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    result = main([
        "generate",
        "--lit-verdict-file", str(FIXTURE),
        "--provider", "online_llm",
        "--model", "enabled-generic-test",
        "--models-file", str(models_file),
        "--output-root", str(tmp_path / "output"),
    ])
    assert result == 1
    stdout = capsys.readouterr().out
    assert "Status: blocked" in stdout
    receipts = list((tmp_path / "output" / "creative_angle_packs").glob("*/ANGLE_PACK_RECEIPT.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["network_called"] is False
    assert receipt["schema_valid"] is False
    assert receipt["redacted_error"]
    assert calls == []


def test_cli_online_mode_refuses_without_config(tmp_path, monkeypatch, capsys):
    for name in ("CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY", "CREATIVE_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    result = main([
        "generate",
        "--lit-verdict-file", str(FIXTURE),
        "--provider", "online_llm",
        "--models-file", str(tmp_path / "missing.json"),
        "--output-root", str(tmp_path / "output"),
    ])
    stderr = capsys.readouterr().err
    assert result == 1
    assert "online_llm requires --model" in stderr


def test_deterministic_vs_online_comparison_receipt(tmp_path):
    output, _, deterministic = _generate(tmp_path)
    profile = LLMModelRegistry(local_path=NO_LOCAL_MODELS).require("fake-json-model", require_json_schema=True)
    provider = OnlineLLMCreativeGenerationProvider(profile, FakeLLMAdapter())
    _, _, online = _generate(tmp_path, provider, online_explicit=True)
    comparator = CreativePackComparator(output_root=output, now=lambda: NOW)
    receipt, path = comparator.compare(
        left=output / deterministic.artifacts["creative_angle_pack"],
        right=output / online.artifacts["creative_angle_pack"],
    )
    assert path.is_file()
    assert receipt["status"] == "completed"
    assert len(receipt["angle_comparisons"]) == 5
    assert receipt["angle_uniqueness"] == {"left": True, "right": True}
    assert receipt["longform_completeness"] == {"left": True, "right": True}
    assert receipt["quality_gate_result"] == {"left": True, "right": True}
    assert receipt["safety"]["network_called"] is False
    assert receipt["safety"]["publish_attempted"] is False
