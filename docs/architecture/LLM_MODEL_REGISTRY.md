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
safety notes, enabled state, and the provider-facing `provider_model`. Credential-like
fields are rejected even in local profile files.

## Preferred free routes

`openrouter-free` is the preferred first remote route. It uses
`provider_model: openrouter/free`, requires `OPENROUTER_API_KEY`, and reads its
HTTPS base URL from `OPENROUTER_BASE_URL`. Optional `OPENROUTER_HTTP_REFERER`
and `OPENROUTER_APP_TITLE` values add attribution headers but are never required
or persisted.

`ollama-local` is the preferred no-cloud route. It defaults to
`provider_model: llama3.1:8b`, needs no API key, and reads `OLLAMA_BASE_URL`.
Plain HTTP is accepted only because this profile explicitly enables localhost,
and then only for `localhost`, `127.0.0.1`, or `::1`. Arbitrary remote HTTP is
always refused.

Free routes can be rate-limited or unavailable, and open models may return less
reliable JSON. Server-side structured output never replaces the strict local
schema and quality gates. Hugging Face can be added as an operator-reviewed
generic OpenAI-compatible profile when a chosen endpoint matches this adapter;
it is documented only and has no built-in profile because endpoint behavior and
authentication vary.

## Add or switch a model

1. Initialize the ignored profile template or copy an example:

```powershell
python llm_models.py init-local-config
```

   The initializer confirms Git ignore protection and refuses overwrite without
   `--force`. It writes `api_key_env`/`base_url_env` names only.
2. Edit `.local/llm/models.json`.
3. Give it a unique `model_id`, correct capabilities/limits/pricing, and review
   its safety notes.
4. Set `enabled: true` only after review.
5. Export the variables named by `base_url_env` and `api_key_env`. A null
   `api_key_env` is allowed only for a reviewed keyless route such as local
   Ollama. Environment-variable names are configuration; values never belong in
   the registry.
6. Validate and inspect:

```powershell
python llm_models.py validate-config
python llm_models.py show --model openrouter-free
python llm_models.py show --model ollama-local
python llm_models.py show --model <model_id>
python llm_models.py test --model <model_id> --dry-run
```

7. Select it explicitly:

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
