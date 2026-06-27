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
python -m playwright install chromium
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

## Phase 2B: controlled LIT app recording

Start the local LIT app, then request one explicit recording run:

```powershell
cd "C:\repos\LIT-GhostTown"
npm run dev
```

```powershell
cd "C:\repos\Shorts Factory"
$env:LIT_APP_URL="http://127.0.0.1:5173"
python orchestrator.py --batch 1 --locale en-US --mode api --record-app
```

The flag records synthetic seed input only. It creates
`app_recording_raw.webm`, normalized vertical `app_recording.mp4`, and
`app_recording_final.png` beside the existing job artifacts. Recording is off
by default, and a browser/app failure is recorded as a receipt warning without
breaking short generation.

## Phase 2C: local voiceover

Voiceover is opt-in and leaves the existing `short.mp4` unchanged:

```powershell
python orchestrator.py --batch 1 --locale en-US --mode api --tts
python orchestrator.py --batch 1 --locale en-US --mode api --record-app --tts
```

The default `TTS_PROVIDER=auto` uses Windows SAPI on Windows and `pyttsx3`
when available on other platforms. It requires no paid credentials. Set
`TTS_VOICE` to an installed local voice name to override the system default.
Provider failures are non-fatal by default: the job creates audible
`voiceover.wav` fallback audio and records the warning in `receipt.json`. Set
`TTS_STRICT=true` to make provider or muxing failures fail the run.

An enabled run adds `voiceover.wav` and `short_with_voice.mp4`. Verify the AAC
audio stream with:

```powershell
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,duration -of json output/jobs/<job_id>/short_with_voice.mp4
```

## Phase 2D: background music mix

Music is also opt-in. Use it with TTS to keep the voiceover and add a quiet
background bed:

```powershell
python orchestrator.py --batch 1 --locale en-US --mode api --record-app --tts --music
```

By default, `MUSIC_SOURCE=generated` creates a deterministic, royalty-safe
ambient WAV locally. Set `MUSIC_SOURCE=local` and `MUSIC_PATH` to use a local
audio file after ffprobe validation. `MUSIC_VOLUME=0.12` keeps the bed below
the existing voiceover. If a configured local file is missing or invalid, the
non-strict default generates fallback music and records a receipt warning;
`MUSIC_STRICT=true` makes that error fatal.

The music run adds `background_music.wav` (or a copied local audio file) and
`short_with_voice_and_music.mp4`, while preserving all earlier outputs. Verify
the final AAC stream with:

```powershell
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,duration -of json output/jobs/<job_id>/short_with_voice_and_music.mp4
```

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
- Real localization.
- Queue and scheduler.
- Publisher integrations.
