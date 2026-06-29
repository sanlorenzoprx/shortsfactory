# LIT Verdict Contract

## Ownership

LIT-GhostTown evaluates an idea. Shorts Factory consumes the validated
structured verdict and packages it into content. Shorts Factory does not invent
or repair business conclusions.

## Required legacy fields

- `verdict_headline`
- `lit_score` (integer 0-100)
- `risk_level`
- `top_reason`
- `next_step`
- `source`

## Rich Phase 4F fields

- `ghost_town_risk`
- `buyer_pain_clarity`
- `willingness_to_pay_signal`
- `distribution_difficulty`
- `unfair_advantage_check`
- `business_model_weakness`
- `why_it_might_work`
- `why_it_might_fail`
- `killer_question`
- `mvp_test`
- `warnings`
- `provenance`

Risk fields use `low | medium | high`. Signal fields use
`weak | medium | strong`. Warnings are strings.

## Validation rules

All rich fields are required for a verdict to be marked rich. Text must be
specific and non-empty. LIT rejects unknown fields, out-of-range scores, invalid
enums, non-array warnings, malformed provenance, generic advice, fake certainty,
and unsupported market/statistical claims.

The evaluator treats user input as supplied evidence, not verified market fact.
It does not add external statistics.

## Provenance and fallback

Validated rich responses record:

```json
{
  "source": "ai_verdict_engine",
  "provider": "mock",
  "model": "mock-lit-verdict-v1",
  "validated": true,
  "rich_verdict": true
}
```

If rich fields are missing or invalid but legacy fields remain valid, Shorts
Factory preserves the legacy verdict and records `rich_verdict: false` plus
`rich_verdict_fields_missing` or `rich_verdict_invalid`. If a required
legacy field is invalid, the existing deterministic `api_fallback` behavior
remains authoritative.

## Template context

Rich fields are allowlisted as inert text placeholders. They cannot execute
code or bypass review/export gates. Existing templates continue to work.

## Safety boundary

This contract adds no publishing, platform API, OAuth, scraping, upload,
external database, or social-engagement automation.
