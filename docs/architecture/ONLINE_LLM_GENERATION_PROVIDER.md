# Online LLM Generation Provider

`CreativeGenerationProvider` separates creative generation from orchestration.
It exposes angle-pack, short-script, title, thumbnail, caption, YouTube metadata,
and long-form generation methods. Three provider modes implement the boundary:

- `deterministic`: default local templates; no key and no network.
- `fixture`: checked-in verdict and generated-output regression data; no network.
- `online_llm`: optional explicit structured-JSON HTTP adapter.

## Explicit online configuration

Set `CREATIVE_LLM_API_URL`, `CREATIVE_LLM_API_KEY`, and
`CREATIVE_LLM_MODEL`, or create the ignored local file:

```json
{
  "api_url": "https://provider.example/v1/chat/completions",
  "api_key": "local-secret",
  "model_id": "provider-model-id",
  "timeout_seconds": 45
}
```

Then select online mode explicitly:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model <model_id>
```

The adapter sends an evidence-bounded system prefix and requests a JSON object.
The endpoint must return structured content through a direct `result`/`output`,
an OpenAI-compatible `choices[0].message.content`, or `output_text` envelope.
Provider-specific capabilities beyond this HTTP contract are not assumed.

## Fail-closed behavior

- Online mode is never selected by default.
- Missing URL, key, or model refuses before network access.
- Provider input containing detected secrets/authentication URLs is refused.
- Raw responses and API keys are never persisted.
- Only schema-valid, gate-passing output becomes a creative artifact.
- Invalid output produces a redacted blocked receipt and no short/long-form files.
- Token use is recorded only when returned as a numeric summary; cost remains
  optional and does not control orchestration.
- LLM output cannot approve, publish, fetch analytics, or alter autopilot mode.

Tests use deterministic and fixture providers only. The missing-config refusal
test proves that online mode makes no request.
