# Online LLM Generation Provider

`CreativeGenerationProvider` separates creative generation from orchestration.
It exposes angle-pack, short-script, title, thumbnail, caption, YouTube metadata,
and long-form generation methods. Three provider modes implement the boundary:

- `deterministic`: default local templates; no key and no network.
- `fixture`: checked-in verdict and generated-output regression data; no network.
- `online_llm`: optional explicit structured-JSON HTTP adapter.

## Explicit online configuration

Phase 5B.5A resolves `--model` through `LLMModelRegistry`. Safe examples live
in `config/examples/llm_models.example.json`; additions and overrides belong in
ignored `.local/llm/models.json`. Profiles never contain credentials. Generic
HTTP adapters read the exact environment-variable names declared by each
profile.

OpenRouter is the first recommended cloud provider. Creative generation uses
the ordered `openrouter-free-creative-chain`; `openrouter/free` is only its last
fallback because automatic routing can choose an unsuitable model. Register with
OpenRouter, create a new API key, and revoke any key that was pasted into chat
or otherwise exposed. Keep the new key only in the current PowerShell session
or an ignored environment file:

```powershell
$env:OPENROUTER_API_KEY="<key>"
$env:OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
$env:OPENROUTER_HTTP_REFERER="https://ghosttowntest.com" # optional
$env:OPENROUTER_APP_TITLE="Ghost Town Test"              # optional

python llm_models.py test-fallback --fallback-group openrouter-free-creative-chain --dry-run
```

The preferred no-cloud profile is `ollama-local`:

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434/v1"
```

The chain tries the two Gemma profiles, Llama 3.3 70B, and GPT OSS 120B before
the automatic router. Prefer explicit `:free` slugs to avoid accidental paid
usage. If OpenRouter rejects a slug, correct that profile in ignored
`.local/llm/models.json`. BytePlus ModelArk and self-hosted HTTPS endpoints
remain future provider profiles.

Every attempt uses one strict-JSON request with `temperature: 0.2` and
`stream: false`. The adapter does not send `reasoning.enabled`; raw provider
responses and `reasoning_details` are never stored.

OpenRouter free capacity can be rate-limited or unavailable. Ollama and other
free/open models may be weaker at structured JSON. Both still pass the same
strict client-side schema and creative quality gates. Hugging Face is a
documentation-only generic-profile option when a specific endpoint is cleanly
OpenAI compatible; there is no built-in route.

Then select online mode explicitly:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model <model_id>
```

The selected adapter receives an evidence-bounded prompt, a task schema, and the
validated model profile. Generic HTTP endpoints must return structured content
through a direct `result`/`output`, an OpenAI-compatible
`choices[0].message.content`, or `output_text` envelope. Provider-specific
capabilities beyond the adapter contract are not assumed.

Phase 5B.5B uses one `generate_creative_bundle` request per pack. Its prompt
contains only the stable prefix, one LIT verdict object, required five-angle
rubric, Ghost Town Test brand/audience context, and constraints requiring five
shorts, one long-form plan, draft metadata, the canonical CTA, no publishing,
and no invented claims. The output schema covers the complete bundle. Source
receipt paths, local files, environment files, YouTube credentials, upload
receipts, and repository secrets are never included.

## Fail-closed behavior

- Online mode is never selected by default.
- Missing, disabled, or schema-incapable model profiles refuse before generation.
- Missing generic-provider URL or key refuses before network access.
- Remote endpoints require HTTPS. Loopback HTTP is accepted only by an
  explicitly local profile and only for localhost/127.0.0.1/::1.
- Provider input containing detected secrets/authentication URLs is refused.
- Raw responses and API keys are never persisted.
- Only schema-valid, gate-passing output becomes a creative artifact.
- Invalid output produces a redacted blocked receipt and no short/long-form files.
- Token use is recorded only when returned as a numeric summary; cost remains
  optional and does not control orchestration.
- LLM output cannot approve, publish, fetch analytics, or alter autopilot mode.
- Attempt receipts explicitly record schema status, redacted error, network,
  YouTube API, `videos.insert`, publishing, secret, and raw-response flags.

Tests use deterministic, fake, and fixture adapters only. Fake online generation
exercises the complete registry/provider/schema path without a network request.
See `docs/architecture/LLM_MODEL_REGISTRY.md`.
