# Experiments

## E001 — Local mock video generation

Result: worked

Evidence:
- Real `script.txt`
- Real `captions.srt`
- Real `thumbnail.jpg`
- Real 1080×1920 H.264 MP4
- Real `receipt.json`
- Tests passed

Notes:
This established the boring MVP foundation.

## E002 — LIT API fallback

Result: worked

Evidence:
- API mode completes when the LIT endpoint is unavailable.
- `receipt.json` records `api_fallback` warning.

Notes:
This protects the pipeline from endpoint outages.

## E003 — Real local LIT API mode

Result: worked

Evidence:
- Verdict source can be `lit_api`.
- Raw `lit_api_response.json` is saved on success.
- Output short is generated from API content.

## E004 — Playwright app recording

Result: worked after selector fix

Problem:
`[name="description"]` matched the page meta description and caused ambiguous Playwright fill behavior.

Fix:
Use stable app selectors / test IDs.

Evidence:
- `app_recording_raw.webm`
- `app_recording.mp4`
- `app_recording_final.png`
- `recording.status: success`
- 1080×1920 verified

## E005 — Real SAPI voiceover

Result: worked

Evidence:
- PCM WAV voiceover
- Final MP4 includes AAC audio
- Phase 2C commit: `bd8d3e3`
- Reported validation: 23 tests passed
- Reported voiceover duration: 25.216s

## E006 — Background music mix

Result: worked

Evidence:
- H.264 1080×1920 final MP4 with AAC audio
- Voice retention correlation: 0.997021
- Phase 2D commit: `b2a1759`
- Reported validation: 27 tests passed

## E007 — Real localization

Result: worked

Evidence:
- Phase 2E commit: `53a2b4f`
- Deterministic localized verdict feeds script, captions, thumbnail, video scenes, TTS text, and publisher metadata.
- Unsupported locales fall back with receipt warnings.
- Finite phrase catalog used instead of LLM/translation service.

## E008 — Local queue and scheduler

Result: worked

Evidence:
- Phase 2F commit: `a3edbba`
- Local queue/scheduler implemented.
- Single-process limitation intentionally accepted.

## E009 — Dry-run publisher packages

Result: worked

Evidence:
- Phase 2G commit: `48fb757`
- Final tests: 44 passed
- Final media: H.264/AAC, 1080×1920
- Live publishing remains disabled and explicitly refused.
- Publisher packages require human approval.
