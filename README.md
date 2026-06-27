# Shorts Factory MVP Repo

This is the boring, working MVP pipeline for the LIT Ghost Town Shorts Factory.

## First win

Generate one real local mock Short with no external API keys:

```bash
python orchestrator.py --batch 1 --locale en-US --mode mock
```

Expected files:

```txt
output/jobs/<job_id>/short.mp4
output/jobs/<job_id>/thumbnail.jpg
output/jobs/<job_id>/captions.srt
output/jobs/<job_id>/script.txt
output/jobs/<job_id>/receipt.json
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
python orchestrator.py --batch 1 --locale en-US --mode mock
```

The video step requires `ffmpeg` on `PATH`. No API keys or network connection
are needed when the pipeline runs in mock mode.

## Phase 2A: LIT API mode

Set the LIT endpoint in `.env`, then run the same pipeline in API mode:

```env
LIT_API_URL=http://localhost:8787/api/verdict
LIT_API_TIMEOUT_SECONDS=20
LIT_API_KEY=
```

```bash
python orchestrator.py --batch 1 --locale en-US --mode api
```

API mode sends the complete idea, locale, `source: shorts_factory`, and the
deterministic 15-answer test payload.
When `LIT_API_KEY` is non-empty, it is sent as a Bearer token. Successful API
runs normalize top-level, `deterministicScores`, `result`, and `verdict`
response shapes and save the original response as `lit_api_response.json`.

If the endpoint is unavailable, times out, or returns an incomplete verdict,
the job still completes with a deterministic `api_fallback` verdict and records
the reason in `receipt.json`. Mock mode never calls the API.

## Rules

Do not add publishing, TikTok API, paid TTS, real trend scraping, or G20 scaling until the local mock pipeline and tests pass.

## What this MVP does

- Creates deterministic seed ideas.
- Creates a mock LIT verdict.
- Writes a short script.
- Writes captions.
- Creates a thumbnail.
- Creates a real vertical MP4 using Pillow-rendered scenes + ffmpeg.
- Writes a receipt JSON.

## What comes later

- Deployed LIT API configuration.
- Playwright app recording.
- Real voiceover/TTS.
- Background music and audio mix.
- Real localization.
- Queue and scheduler.
- Publisher integrations.
