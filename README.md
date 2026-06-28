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

## Phase 2E: deterministic localization

`en-US` and practical Puerto Rico Spanish (`es-PR`) are supported without an
LLM or translation API. Spanish aliases `es`, `es-US`, and `es-ES` resolve to
`es-PR`:

```powershell
python orchestrator.py --batch 1 --locale es-PR --mode mock
python orchestrator.py --batch 1 --locale es-PR --mode api --record-app --tts --music
```

The script, captions, thumbnail, rendered video scenes, and TTS input use the
resolved locale. Unsupported locales safely fall back to `en-US`; missing
catalog phrases stay in English and are listed in `receipt.json.localization`
and the top-level receipt warnings.

## Phase 2F: local queue and scheduler

The queue is a single-process, durable local JSON file—not a cloud worker or
distributed system. Enqueue work, then run it once:

```powershell
python orchestrator.py --enqueue --batch 3 --locale en-US --mode mock
python orchestrator.py --run-queue --max-jobs 3
```

Queue jobs keep a stable output job ID across retries, stop retrying at
`--max-attempts` (default 3), and add attempt/timestamp metadata to the job
receipt. Succeeded jobs are ignored on later queue runs.

Local one-shot schedules live at `output/schedules/schedules.json` by default.
Each enabled entry uses an ISO `due_at` plus the normal `locale`, `mode`,
`record_app`, `tts`, and `music` options. Previewing never enqueues or renders:

```powershell
python orchestrator.py --schedule-dry-run
python orchestrator.py --run-due --max-jobs 3
```

Pass `--schedule-file schedules.example.json` to preview the checked-in example.

`--run-due` marks each due schedule after enqueueing so it cannot duplicate the
same scheduled work. No daemon, hosted scheduler, Redis, or cloud queue is used.

## Phase 2G: dry-run publisher packages

Publisher mode prepares local upload metadata and never posts to a live account:

```powershell
python orchestrator.py --batch 1 --locale en-US --mode api --record-app --tts --music --publish-dry-run
```

Each job gets `publish/publisher_plan.json` plus `metadata.json` and a copied
`captions.srt` for `youtube_shorts`, `tiktok`, and `instagram_reels`. The
manifests reference the existing final MP4 and thumbnail, so large media files
are not duplicated. Every package records `live_publish_enabled: false` and
requires human approval.

Dry-run publishing also works through the local queue:

```powershell
python orchestrator.py --enqueue --batch 1 --locale es-PR --mode mock --tts --music --publish-dry-run
python orchestrator.py --run-queue --max-jobs 1
```

There are no OAuth flows, upload tokens, platform API clients, or live posting
commands in Phase 2G. Attempts to invoke the publisher's live path are refused.

## Phase 3A: local Mission Control

Start the local review dashboard against generated output:

```powershell
python mission_control.py --output-root output
```

Mission Control listens on `http://127.0.0.1:8765` by default. It indexes
receipt-backed jobs under `output/jobs/` and
`output/phase2g-acceptance/jobs/`, then previews available video, thumbnail,
script, captions, receipt, warnings, and dry-run publisher package artifacts.

Review actions are local only. Approve, Reject, Needs Revision, and Reset to
Pending write one JSON record per job under `output/approvals/`. Mission Control
does not publish, call a platform API, authenticate a platform account, or send
job data off the machine.

```powershell
python mission_control.py --output-root output --host 127.0.0.1 --port 8765
python mission_control.py --help
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
