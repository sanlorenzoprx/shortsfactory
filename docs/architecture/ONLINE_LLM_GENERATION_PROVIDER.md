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
HTTP adapters read provider-specific `LLM_<PROVIDER>_API_URL` and
`LLM_<PROVIDER>_API_KEY` environment variables.

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

## Fail-closed behavior

- Online mode is never selected by default.
- Missing, disabled, or schema-incapable model profiles refuse before generation.
- Missing generic-provider URL or key refuses before network access.
- Provider input containing detected secrets/authentication URLs is refused.
- Raw responses and API keys are never persisted.
- Only schema-valid, gate-passing output becomes a creative artifact.
- Invalid output produces a redacted blocked receipt and no short/long-form files.
- Token use is recorded only when returned as a numeric summary; cost remains
  optional and does not control orchestration.
- LLM output cannot approve, publish, fetch analytics, or alter autopilot mode.

Tests use deterministic, fake, and fixture adapters only. Fake online generation
exercises the complete registry/provider/schema path without a network request.
See `docs/architecture/LLM_MODEL_REGISTRY.md`.
