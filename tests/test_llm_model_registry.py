from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_factory.autopilot.llm_model_registry import (
    LLMModelRegistry,
    LLMModelRegistryError,
)
from content_factory.autopilot.llm_models_cli import main
from content_factory.autopilot.llm_provider_adapters import (
    FakeLLMAdapter,
    GenericHTTPAdapter,
    LLMAdapterError,
    LocalFixtureLLMAdapter,
    build_llm_adapter,
)


EXAMPLE = Path("config/examples/llm_models.example.json")


def test_registry_loads_safe_example_profiles():
    registry = LLMModelRegistry()
    profiles = registry.list_profiles()
    assert len(profiles) == 4
    fake = registry.require("fake-json-model", require_json_schema=True)
    assert fake.provider == "fake"
    assert fake.endpoint_type == "fake_json"
    assert fake.supports_json_schema is True
    assert fake.max_input_tokens == 32000
    assert fake.latency_class == "fast"
    assert "scripts" in fake.recommended_for
    assert len(fake.profile_hash) == 64


def test_registry_refuses_missing_disabled_and_schema_incapable_models():
    registry = LLMModelRegistry()
    with pytest.raises(LLMModelRegistryError, match="model not found"):
        registry.require("missing-model")
    with pytest.raises(LLMModelRegistryError, match="disabled"):
        registry.require("generic-http-example")
    with pytest.raises(LLMModelRegistryError, match="lacks required JSON schema"):
        registry.require(
            "no-schema-example", require_enabled=False, require_json_schema=True,
        )


def test_local_registry_overrides_example_without_credentials(tmp_path):
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    override = dict(example["models"][2])
    override.update({"model_id": "local-model", "enabled": True, "provider": "local_provider"})
    local = tmp_path / "models.json"
    local.write_text(json.dumps({"models": [override]}), encoding="utf-8")
    registry = LLMModelRegistry(local_path=local)
    profile = registry.require("local-model", require_json_schema=True)
    assert profile.enabled is True
    assert profile.provider == "local_provider"


def test_registry_rejects_credential_fields_even_in_local_config(tmp_path):
    local = tmp_path / "models.json"
    local.write_text(json.dumps({"models": [{"api_key": "never-store"}]}), encoding="utf-8")
    with pytest.raises(LLMModelRegistryError, match="must not contain credentials"):
        LLMModelRegistry(local_path=local)


def test_fake_and_fixture_adapter_healthchecks_are_offline():
    fake = FakeLLMAdapter()
    fixture = LocalFixtureLLMAdapter()
    assert fake.healthcheck()["status"] == "ready"
    assert fixture.healthcheck()["status"] == "ready"
    assert fake.network_called is fixture.network_called is False
    assert fake.redact_response({"ok": True})["raw_response_stored"] is False


def test_generic_http_adapter_refuses_missing_credentials_without_network(monkeypatch):
    profile = LLMModelRegistry().get("generic-http-example")
    for name in (
        "LLM_EXAMPLE_PROVIDER_API_URL", "LLM_EXAMPLE_PROVIDER_API_KEY",
        "CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMAdapterError, match="requires provider API URL"):
        build_llm_adapter(profile, allow_network=True, require_config=True)


def test_model_cli_list_show_validate_and_dry_test_make_no_network(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert main(["list"]) == 0
    listed = capsys.readouterr().out
    assert "fake-json-model" in listed
    assert main(["show", "--model", "fake-json-model"]) == 0
    shown = capsys.readouterr().out
    assert "model_profile_hash" in shown
    assert main(["validate-config"]) == 0
    validated = capsys.readouterr().out
    assert '"status": "valid"' in validated
    assert main(["test", "--model", "fake-json-model", "--dry-run"]) == 0
    tested = capsys.readouterr().out
    assert '"network_called": false' in tested
    assert calls == []


def test_cost_estimation_uses_profile_rates():
    profile = LLMModelRegistry().require("fake-json-model")
    assert GenericHTTPAdapter(endpoint_url=None, api_key=None).estimate_cost(100, 100, profile) == 0
