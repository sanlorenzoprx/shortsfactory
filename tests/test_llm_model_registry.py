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
NO_LOCAL = Path("tests/fixtures/llm_models.none.json")


def _registry():
    return LLMModelRegistry(local_path=NO_LOCAL)


def test_registry_loads_safe_example_profiles():
    registry = _registry()
    profiles = registry.list_profiles()
    assert len(profiles) == 6
    fake = registry.require("fake-json-model", require_json_schema=True)
    assert fake.provider == "fake"
    assert fake.endpoint_type == "fake_json"
    assert fake.supports_json_schema is True
    assert fake.max_input_tokens == 32000
    assert fake.latency_class == "fast"
    assert "scripts" in fake.recommended_for
    assert len(fake.profile_hash) == 64


def test_free_openrouter_and_local_ollama_profiles_load():
    registry = _registry()
    openrouter = registry.require("openrouter-free", require_json_schema=True)
    assert openrouter.provider == "openrouter"
    assert openrouter.provider_model == "openrouter/free"
    assert openrouter.api_key_env == "OPENROUTER_API_KEY"
    assert openrouter.base_url_env == "OPENROUTER_BASE_URL"
    assert openrouter.allow_localhost is False
    assert openrouter.cost_per_1m_input_tokens == 0

    ollama = registry.require("ollama-local", require_json_schema=True)
    assert ollama.provider_model == "llama3.1:8b"
    assert ollama.api_key_env is None
    assert ollama.base_url_env == "OLLAMA_BASE_URL"
    assert ollama.allow_localhost is True
    assert ollama.supports_json_schema is False


def test_registry_refuses_missing_disabled_and_schema_incapable_models():
    registry = _registry()
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


def test_registry_refuses_missing_provider_model(tmp_path):
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    profile = dict(example["models"][2])
    profile.pop("provider_model")
    profile.update({"model_id": "missing-provider-model", "enabled": True})
    local = tmp_path / "models.json"
    local.write_text(json.dumps({"models": [profile]}), encoding="utf-8")
    with pytest.raises(LLMModelRegistryError, match="provider_model is required"):
        LLMModelRegistry(local_path=local)


def test_init_local_config_writes_env_names_without_keys_and_refuses_overwrite(tmp_path):
    path = tmp_path / ".local" / "llm" / "models.json"
    created = LLMModelRegistry.init_local_config(
        local_path=path,
        ignore_checker=lambda _: True,
    )
    value = json.loads(created.read_text(encoding="utf-8"))
    encoded = created.read_text(encoding="utf-8")
    profile = value["models"][0]
    assert profile["model_id"] == "real-creative-model"
    assert profile["endpoint_type"] == "chat_json"
    assert profile["api_key_env"] == "LLM_API_KEY"
    assert profile["base_url_env"] == "LLM_BASE_URL"
    assert '"api_key"' not in encoded
    assert '"base_url"' not in encoded
    with pytest.raises(LLMModelRegistryError, match="already exists"):
        LLMModelRegistry.init_local_config(local_path=path, ignore_checker=lambda _: True)
    assert LLMModelRegistry.init_local_config(
        local_path=path, force=True, ignore_checker=lambda _: True,
    ) == path


def test_init_local_config_refuses_unignored_path(tmp_path):
    with pytest.raises(LLMModelRegistryError, match="not protected"):
        LLMModelRegistry.init_local_config(
            local_path=tmp_path / "models.json",
            ignore_checker=lambda _: False,
        )


def test_fake_and_fixture_adapter_healthchecks_are_offline():
    fake = FakeLLMAdapter()
    fixture = LocalFixtureLLMAdapter()
    assert fake.healthcheck()["status"] == "ready"
    assert fixture.healthcheck()["status"] == "ready"
    assert fake.network_called is fixture.network_called is False
    assert fake.redact_response({"ok": True})["raw_response_stored"] is False


def test_generic_http_adapter_refuses_missing_credentials_without_network(monkeypatch):
    profile = _registry().get("generic-http-example")
    for name in (
        "LLM_EXAMPLE_PROVIDER_API_URL", "LLM_EXAMPLE_PROVIDER_API_KEY",
        "CREATIVE_LLM_API_URL", "CREATIVE_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMAdapterError, match="requires provider API URL"):
        build_llm_adapter(profile, allow_network=True, require_config=True)


def test_openrouter_requires_api_key_and_supports_optional_attribution(monkeypatch):
    profile = _registry().require("openrouter-free")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMAdapterError, match="requires provider API key"):
        build_llm_adapter(profile, allow_network=False, require_config=True)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://ghosttowntest.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "Ghost Town Test")
    adapter = build_llm_adapter(profile, allow_network=False, require_config=True)
    assert adapter._headers() == {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-only-key",
        "HTTP-Referer": "https://ghosttowntest.com",
        "X-Title": "Ghost Town Test",
    }
    assert adapter.network_called is False

    adapter.http_referer = "https://ghosttowntest.com\r\nX-Injected: unsafe"
    with pytest.raises(LLMAdapterError, match="referer must be a safe HTTPS URL"):
        adapter._headers()


def test_openrouter_requires_https_base_url(monkeypatch):
    profile = _registry().require("openrouter-free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://openrouter.ai/api/v1")
    with pytest.raises(LLMAdapterError, match="must use HTTPS"):
        build_llm_adapter(profile, allow_network=False, require_config=True)


def test_ollama_requires_no_key_and_accepts_explicit_loopback_only(monkeypatch):
    profile = _registry().require("ollama-local", require_json_schema=True)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    adapter = build_llm_adapter(profile, allow_network=False, require_config=True)
    assert "Authorization" not in adapter._headers()
    assert adapter.healthcheck()["status"] == "ready"
    assert adapter.network_called is False

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://models.example/v1")
    with pytest.raises(LLMAdapterError, match="must use HTTPS"):
        build_llm_adapter(profile, allow_network=False, require_config=True)


def test_localhost_http_is_refused_without_explicit_local_profile():
    remote_profile_adapter = GenericHTTPAdapter(
        endpoint_url="http://127.0.0.1:11434/v1",
        api_key="test-only-key",
        allow_localhost=False,
    )
    with pytest.raises(LLMAdapterError, match="must use HTTPS"):
        remote_profile_adapter._validate_config()

    local_profile_adapter = GenericHTTPAdapter(
        endpoint_url="http://127.0.0.1:11434/v1",
        api_key=None,
        api_key_required=False,
        allow_localhost=True,
    )
    local_profile_adapter._validate_config()
    assert local_profile_adapter.network_called is False


def test_model_cli_list_show_validate_and_dry_test_make_no_network(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    registry_args = ["--models-file", str(tmp_path / "missing-models.json")]
    assert main([*registry_args, "list"]) == 0
    listed = capsys.readouterr().out
    assert "fake-json-model" in listed
    assert main([*registry_args, "show", "--model", "fake-json-model"]) == 0
    shown = capsys.readouterr().out
    assert "model_profile_hash" in shown
    assert main([*registry_args, "validate-config"]) == 0
    validated = capsys.readouterr().out
    assert '"status": "valid"' in validated
    assert main([*registry_args, "test", "--model", "fake-json-model", "--dry-run"]) == 0
    tested = capsys.readouterr().out
    assert '"network_called": false' in tested
    assert calls == []


def test_model_cli_free_route_dry_runs_need_no_network_or_credentials(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: calls.append((args, kwargs)))
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    registry_args = ["--models-file", str(tmp_path / "missing-models.json")]
    assert main([*registry_args, "test", "--model", "openrouter-free", "--dry-run"]) == 0
    assert '"runtime_configuration_status": "blocked_missing_config"' in capsys.readouterr().out
    assert main([*registry_args, "test", "--model", "ollama-local", "--dry-run"]) == 0
    assert '"network_called": false' in capsys.readouterr().out
    assert calls == []


def test_model_cli_init_local_config_reports_safe_creation(tmp_path, monkeypatch, capsys):
    path = tmp_path / ".local" / "llm" / "models.json"
    monkeypatch.setattr(LLMModelRegistry, "_git_ignored", staticmethod(lambda _: True))
    assert main(["--models-file", str(path), "init-local-config"]) == 0
    output = capsys.readouterr().out
    assert '"git_ignored": true' in output
    assert '"credentials_included": false' in output


def test_cost_estimation_uses_profile_rates():
    profile = _registry().require("fake-json-model")
    assert GenericHTTPAdapter(endpoint_url=None, api_key=None).estimate_cost(100, 100, profile) == 0


def test_chat_json_adapter_expands_base_url_without_network():
    adapter = GenericHTTPAdapter(
        endpoint_url="https://provider.example/v1",
        api_key="test-only-key",
        endpoint_type="chat_json",
    )
    assert adapter._request_url() == "https://provider.example/v1/chat/completions"
    assert adapter.network_called is False


def test_openrouter_chat_request_is_non_streaming_and_drops_reasoning_details(monkeypatch):
    profile = _registry().require("openrouter-free", require_json_schema=True)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    requests = []

    def transport(**request):
        requests.append(request)
        return {
            "choices": [{
                "message": {
                    "content": '{"ok": true}',
                    "reasoning_details": [{"type": "hidden", "text": "do not retain"}],
                },
            }],
            "usage": {"total_tokens": 12},
        }

    adapter = build_llm_adapter(
        profile,
        allow_network=True,
        require_config=True,
        transport=transport,
    )
    result = adapter.generate_json(
        '{"task":"test"}',
        {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        profile,
    )

    assert result == {"ok": True}
    assert len(requests) == 1
    request = requests[0]
    assert request["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert request["json"]["model"] == "openrouter/free"
    assert request["json"]["temperature"] == 0.2
    assert request["json"]["max_tokens"] == 4000
    assert request["json"]["stream"] is False
    assert "reasoning_details" not in json.dumps(result)
    assert adapter.raw_response_stored is False
