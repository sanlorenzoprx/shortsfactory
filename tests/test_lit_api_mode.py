from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
import requests

from content_factory.agents.app_tester import AppTester
from content_factory.config import Config
from content_factory.integrations.lit_client import LitClient
from content_factory.schemas import Idea
from orchestrator import ContentFactoryOrchestrator


IDEA = Idea(name="API test idea", description="An idea sent to the real LIT API")
CAMEL_CASE_VERDICT = {
    "verdictHeadline": "Test the narrow offer",
    "litScore": 82,
    "riskLevel": "medium",
    "topReason": "The buyer is clear but demand still needs proof.",
    "nextStep": "Pre-sell the smallest useful version.",
}
RICH_VERDICT = {
    "verdict_headline": "Promising, but distribution is the real test.",
    "lit_score": 78,
    "risk_level": "medium",
    "ghost_town_risk": "high",
    "top_reason": "The pain is clear but the buyer path still needs proof.",
    "buyer_pain_clarity": "strong",
    "willingness_to_pay_signal": "weak",
    "distribution_difficulty": "high",
    "unfair_advantage_check": "No durable advantage is established yet.",
    "business_model_weakness": "The offer may be valued as advice rather than software.",
    "why_it_might_work": "Builders can test the costly decision before writing code.",
    "why_it_might_fail": "Interested builders may not pay for the evaluation.",
    "killer_question": "Who needs this urgently enough to pay before building?",
    "mvp_test": "Sell 10 manual evaluations before building software.",
    "next_step": "Offer a paid teardown to 20 targeted builders.",
    "warnings": [],
    "provenance": {
        "source": "ai_verdict_engine",
        "provider": "mock",
        "model": "mock-lit-verdict-v1",
        "generated_at": "2026-01-01T00:00:00.000Z",
        "validated": True,
    },
    "source": "lit_api",
}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "verdict_headline": "Test the narrow offer",
            "lit_score": 82,
            "risk_level": "medium",
            "top_reason": "The buyer is clear but demand still needs proof.",
            "next_step": "Pre-sell the smallest useful version.",
        },
        {"deterministicScores": CAMEL_CASE_VERDICT},
        {"result": CAMEL_CASE_VERDICT},
        {"verdict": CAMEL_CASE_VERDICT},
        {"result": {"deterministicScores": CAMEL_CASE_VERDICT}},
    ],
)
def test_api_mode_normalizes_supported_response_shapes(monkeypatch, payload):
    tester = AppTester(Config(mode="api", lit_api_url="https://lit.example/api/verdict"))
    monkeypatch.setattr(tester.client, "test_idea", lambda idea, locale="en-US": payload)

    outcome = tester.run_test_with_details(IDEA)

    assert outcome.verdict.idea == IDEA
    assert outcome.verdict.verdict_headline == "Test the narrow offer"
    assert outcome.verdict.lit_score == 82
    assert outcome.verdict.risk_level == "medium"
    assert outcome.verdict.top_reason
    assert outcome.verdict.next_step
    assert outcome.verdict.source == "lit_api"
    assert outcome.raw_response == payload
    assert outcome.warning is None


def test_api_mode_falls_back_to_complete_verdict_on_request_failure(monkeypatch):
    tester = AppTester(Config(mode="api", lit_api_url="https://lit.example/api/verdict"))

    def fail(_idea, locale="en-US"):
        raise requests.Timeout("test timeout")

    monkeypatch.setattr(tester.client, "test_idea", fail)
    outcome = tester.run_test_with_details(IDEA)

    assert outcome.verdict.idea == IDEA
    assert outcome.verdict.verdict_headline
    assert isinstance(outcome.verdict.lit_score, int)
    assert outcome.verdict.risk_level
    assert outcome.verdict.top_reason
    assert outcome.verdict.next_step
    assert outcome.verdict.source == "api_fallback"
    assert outcome.raw_response is None
    assert "test timeout" in outcome.warning


def test_api_mode_consumes_valid_rich_verdict_and_provenance(monkeypatch):
    tester = AppTester(Config(mode="api", lit_api_url="https://lit.example/api/verdict"))
    monkeypatch.setattr(tester.client, "test_idea", lambda idea, locale="en-US": RICH_VERDICT)

    outcome = tester.run_test_with_details(IDEA)

    assert outcome.verdict.killer_question == RICH_VERDICT["killer_question"]
    assert outcome.verdict.mvp_test == RICH_VERDICT["mvp_test"]
    assert outcome.verdict.why_it_might_work == RICH_VERDICT["why_it_might_work"]
    assert outcome.verdict.provenance == {
        **RICH_VERDICT["provenance"],
        "rich_verdict": True,
    }
    assert outcome.verdict.warnings == ()


def test_invalid_rich_fields_use_valid_legacy_contract_with_warning(monkeypatch):
    tester = AppTester(Config(mode="api", lit_api_url="https://lit.example/api/verdict"))
    payload = {**RICH_VERDICT, "ghost_town_risk": "certain"}
    monkeypatch.setattr(tester.client, "test_idea", lambda idea, locale="en-US": payload)

    outcome = tester.run_test_with_details(IDEA)

    assert outcome.verdict.source == "lit_api"
    assert outcome.verdict.killer_question == ""
    assert outcome.verdict.provenance == {
        "source": "legacy_lit_api",
        "rich_verdict": False,
    }
    assert outcome.verdict.warnings[0].startswith("rich_verdict_invalid:")


@pytest.mark.parametrize(
    ("api_key", "expected_authorization"),
    [("secret-token", "Bearer secret-token"), ("", None)],
)
def test_lit_client_sends_payload_timeout_and_optional_auth(
    monkeypatch, api_key, expected_authorization
):
    captured: Dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return CAMEL_CASE_VERDICT

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("content_factory.integrations.lit_client.requests.post", fake_post)
    client = LitClient(
        "https://lit.example/api/verdict", timeout_seconds=3.5, api_key=api_key
    )

    assert client.test_idea(IDEA) == CAMEL_CASE_VERDICT
    assert captured["url"] == "https://lit.example/api/verdict"
    assert captured["timeout"] == 3.5
    assert captured["json"]["idea"]["name"] == IDEA.name
    assert len(captured["json"]["answers"]) == 15
    assert captured["json"]["source"] == "shorts_factory"
    assert captured["json"]["locale"] == "en-US"
    assert captured["headers"].get("Authorization") == expected_authorization


def _fast_orchestrator(config: Config, monkeypatch) -> ContentFactoryOrchestrator:
    orchestrator = ContentFactoryOrchestrator(config)

    def create_short(_script, _verdict, job_dir: Path, **_kwargs) -> Path:
        path = job_dir / "short.mp4"
        path.write_bytes(b"test-mp4")
        return path

    monkeypatch.setattr(orchestrator.video, "create_short", create_short)
    return orchestrator


def test_successful_api_run_writes_raw_response_and_no_warning(tmp_path, monkeypatch):
    config = Config(
        mode="api",
        lit_api_url="https://lit.example/api/verdict",
        output_dir=tmp_path / "output",
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    payload = {"result": {"verdict": CAMEL_CASE_VERDICT}}
    monkeypatch.setattr(
        orchestrator.tester.client,
        "test_idea",
        lambda idea, locale="en-US": payload,
    )

    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw_path = Path(receipt["outputs"]["lit_api_response_json"])

    assert receipt["verdict"]["source"] == "lit_api"
    assert receipt["warnings"] == []
    assert receipt["verdict_provenance"] == {
        "source": "legacy_lit_api",
        "rich_verdict": False,
    }
    assert receipt["verdict_warnings"] == ["rich_verdict_fields_missing"]
    assert raw_path.name == "lit_api_response.json"
    assert json.loads(raw_path.read_text(encoding="utf-8")) == payload
    for output_name in (
        "short_mp4",
        "thumbnail_jpg",
        "captions_srt",
        "script_txt",
        "receipt_json",
    ):
        output_path = receipt_path if output_name == "receipt_json" else Path(receipt["outputs"][output_name])
        assert output_path.exists(), output_name
        assert output_path.stat().st_size > 0, output_name


def test_api_fallback_writes_warning_and_no_raw_response(tmp_path, monkeypatch):
    config = Config(
        mode="api",
        lit_api_url="https://lit.example/api/verdict",
        output_dir=tmp_path / "output",
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)

    def fail(_idea, locale="en-US"):
        raise requests.ConnectionError("server unavailable")

    monkeypatch.setattr(orchestrator.tester.client, "test_idea", fail)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["verdict"]["source"] == "api_fallback"
    assert len(receipt["warnings"]) == 1
    assert "server unavailable" in receipt["warnings"][0]
    assert "lit_api_response_json" not in receipt["outputs"]
    assert not (receipt_path.parent / "lit_api_response.json").exists()
    assert receipt["voiceover"] == {"status": "disabled"}
    assert receipt["verdict_provenance"]["source"] == "deterministic_fallback"
    assert receipt["verdict_warnings"] == ["rich_verdict_fields_missing"]


def test_rich_api_receipt_records_validated_provenance(tmp_path, monkeypatch):
    config = Config(
        mode="api",
        lit_api_url="https://lit.example/api/verdict",
        output_dir=tmp_path / "output",
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    monkeypatch.setattr(
        orchestrator.tester.client,
        "test_idea",
        lambda idea, locale="en-US": RICH_VERDICT,
    )

    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["verdict_provenance"] == {
        **RICH_VERDICT["provenance"],
        "rich_verdict": True,
    }
    assert receipt["verdict_warnings"] == []
    assert receipt["verdict"]["killer_question"] == RICH_VERDICT["killer_question"]


def test_orchestrator_passes_requested_locale_to_lit(monkeypatch, tmp_path):
    config = Config(
        mode="api",
        lit_api_url="https://lit.example/api/verdict",
        output_dir=tmp_path / "output",
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    captured = {}

    def respond(_idea, locale="en-US"):
        captured["locale"] = locale
        return CAMEL_CASE_VERDICT

    monkeypatch.setattr(orchestrator.tester.client, "test_idea", respond)
    orchestrator.run_batch(batch=1, locale="es-VE")

    assert captured["locale"] == "es-VE"
