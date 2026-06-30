# LLM Model Registry

Phase 5B.5A makes creative online generation model-agnostic. The creative
engine knows only a selected `LLMModelProfile` and the `LLMProviderAdapter`
interface; endpoint/auth/response details remain inside adapters.

## Registry sources

Safe checked-in examples:

```txt
config/examples/llm_models.example.json
```

Ignored local overrides/additions:

```txt
.local/llm/models.json
```

Local entries override an example with the same `model_id`. Profiles contain
provider identity, endpoint type, JSON-schema/tool capabilities, input/output
limits, optional per-million-token prices, latency class, recommended tasks,
safety notes, and enabled state. Credential-like fields are rejected even in
local profile files.

## Add or switch a model

1. Copy a profile from the example into `.local/llm/models.json`.
2. Give it a unique `model_id`, correct capabilities/limits/pricing, and review
   its safety notes.
3. Set `enabled: true` only after review.
4. For `generic_http`, export `LLM_<PROVIDER>_API_URL` and
   `LLM_<PROVIDER>_API_KEY`, with non-alphanumeric provider characters changed
   to underscores and the name uppercased.
5. Validate and inspect:

```powershell
python llm_models.py validate-config
python llm_models.py show --model <model_id>
python llm_models.py test --model <model_id> --dry-run
```

6. Select it explicitly:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model <model_id>
```

Deterministic generation remains the default:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider deterministic
```

## Adapter boundary

- `FakeLLMAdapter`: offline schema-path smoke and failure-mode testing.
- `LocalFixtureLLMAdapter`: checked-in structured fixture playback.
- `GenericHTTPAdapter`: future JSON-schema HTTP providers; environment-only
  credentials and explicit network permission.

Adapters generate structured candidates, estimate token cost from the selected
profile, redact response summaries, and report health. They cannot approve,
publish, call YouTube APIs, or alter orchestration. Invalid JSON/schema, secrets,
authentication URLs, unsupported claims, publishing instructions, missing or
disabled profiles, and missing capability/configuration fail closed.

API keys must never be committed. `.env`, `.env.local`, and `.local/llm/` are
ignored, and registry profile parsing rejects credential fields.
