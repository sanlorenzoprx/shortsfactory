from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .llm_model_registry import (
    DEFAULT_EXAMPLE_PATH,
    DEFAULT_LOCAL_PATH,
    LLMModelRegistry,
    LLMModelRegistryError,
)
from .llm_provider_adapters import LLMAdapterError, build_llm_adapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the Phase 5B.5A LLM model registry.")
    parser.add_argument("--models-file", default=str(DEFAULT_LOCAL_PATH), help="Ignored local model registry overrides")
    parser.add_argument("--example-models", default=str(DEFAULT_EXAMPLE_PATH), help="Safe checked-in example profiles")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List model profiles without credentials")
    show = commands.add_parser("show", help="Show one redacted model profile")
    show.add_argument("--model", required=True)
    commands.add_parser("validate-config", help="Validate example and local profile files")
    init = commands.add_parser("init-local-config", help="Create an ignored real-model profile template")
    init.add_argument("--force", action="store_true", help="Replace an existing local model profile file")
    test = commands.add_parser("test", help="Test adapter readiness; network is opt-in")
    test.add_argument("--model", required=True)
    mode = test.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate only; never call a network")
    mode.add_argument("--confirm-live-llm-call", action="store_true", help="Explicitly allow one provider test call")
    return parser


def _registry(args: argparse.Namespace) -> LLMModelRegistry:
    return LLMModelRegistry(example_path=args.example_models, local_path=args.models_file)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-local-config":
            path = LLMModelRegistry.init_local_config(
                local_path=args.models_file,
                force=args.force,
            )
            print(json.dumps({
                "status": "created",
                "path": str(path),
                "git_ignored": True,
                "credentials_included": False,
                "credential_source": "environment_variables",
            }, indent=2))
            return 0
        registry = _registry(args)
        if args.command == "list":
            print(json.dumps([
                {
                    "model_id": profile.model_id,
                    "provider": profile.provider,
                    "display_name": profile.display_name,
                    "endpoint_type": profile.endpoint_type,
                    "enabled": profile.enabled,
                    "supports_json_schema": profile.supports_json_schema,
                    "latency_class": profile.latency_class,
                    "recommended_for": list(profile.recommended_for),
                }
                for profile in registry.list_profiles()
            ], indent=2, ensure_ascii=False))
            return 0
        if args.command == "show":
            profile = registry.require(args.model, require_enabled=False)
            print(json.dumps({**profile.to_dict(), "model_profile_hash": profile.profile_hash}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "validate-config":
            print(json.dumps(registry.validate(), indent=2, ensure_ascii=False))
            return 0
        profile = registry.require(args.model, require_json_schema=True)
        adapter = build_llm_adapter(
            profile,
            allow_network=args.confirm_live_llm_call,
            require_config=args.confirm_live_llm_call,
        )
        if args.dry_run:
            health = adapter.healthcheck()
            result = {
                "model_id": profile.model_id,
                "provider": profile.provider,
                "model_profile_hash": profile.profile_hash,
                **{key: value for key, value in health.items() if key != "status"},
                "status": "ready",
                "runtime_configuration_status": health.get("status"),
                "dry_run": True,
                "network_called": False,
            }
        else:
            value = adapter.generate_json(
                json.dumps({"task": "registry_healthcheck", "input": {"message": "Return ok true"}}),
                {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                profile,
            )
            result = {
                "model_id": profile.model_id,
                "provider": profile.provider,
                "model_profile_hash": profile.profile_hash,
                "adapter_type": adapter.adapter_type,
                "status": "completed",
                "response_redaction": adapter.redact_response(value),
                "network_called": adapter.network_called,
                "secrets_recorded": False,
                "raw_response_stored": False,
            }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status") in {"ready", "completed"} else 1
    except (LLMModelRegistryError, LLMAdapterError, OSError, ValueError) as exc:
        print(f"LLM model registry refused: {exc}", file=sys.stderr)
        return 1
