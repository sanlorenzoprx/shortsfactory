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

## Phase 3B: approval-gated local export bundles

Open Mission Control, review a job, and select **Approve**. An approved job can
then be exported from its detail page with **Export Approved Bundle**, or with
the local CLI:

```powershell
python export_bundle.py --job-id <job_id> --output-root output --export-root exports
```

Unapproved jobs are refused. Approved bundles are written deterministically to:

```txt
exports/approved/<job_id>/
```

Each bundle contains the best available video as `final.mp4`, the source
receipt, an unchanged `APPROVAL.json`, an `EXPORT_MANIFEST.json`, and all
available supporting assets. Phase 2G publisher plans are copied locally as
`publisher_package.json` when present.

The manifest always records `publishing_status: not_published` and
`live_publishing_enabled: false`. Export bundles are ignored by Git and are
prepared only for human inspection or manual upload; no platform API, OAuth,
cloud upload, or live publishing is involved.

## Phase 3C: human revision queue

Mission Control can turn a specific human note into a local revision task.
Open a job, enter the requested change under **Human revision**, and select
**Create Revision Task**. This marks the source job Needs Revision. Run the task
from Mission Control or with:

```powershell
python revise_job.py --job-id <job_id> --output-root output
```

The CLI can also create or update a task for a job already marked
`needs_revision`:

```powershell
python revise_job.py --job-id <job_id> --output-root output --note "tighten hook and make CTA clearer"
```

Phase 3C applies small deterministic local rules, regenerates the script,
captions, thumbnail, and basic video, and writes a new normal job under
`output/jobs/<revised_job_id>/`. Its receipt and `REVISION_MANIFEST.json` link
back to the untouched original job.

Every revised job starts with its own pending approval. The original approval
never carries over: review and approve the revised job separately before using
the Phase 3B export action. Revision manifests always state that reapproval is
required, publishing has not occurred, and live publishing is disabled. After
**Run Local Revision** succeeds, Mission Control opens the newly revised job
directly so it can be reviewed and separately approved.

## Phase 3D: deterministic local quality scoring

Score any receipt-backed job with local rules only:

```powershell
python score_job.py --job-id <job_id> --output-root output
python score_job.py --job-id <job_id> --output-root output --json
```

The report is written to `output/quality/<job_id>.json`. Mission Control also
provides **Score Job** and **Re-score Job** actions, shows score/status on the
job index, and displays nine category scores, issues, suggested fixes,
recommended action, approval readiness, and export readiness on job detail.

Scores are deterministic and advisory:

- `pass`: score 80 or higher with no error issue
- `warn`: score 60–79 with no error issue
- `fail`: score below 60 or any error issue

A quality pass means ready for human consideration—not approved. Scoring never
changes approval state, creates an export, or publishes anything. Phase 3B
still requires an explicit approval, and Phase 3C revisions still require
their own separate approval.

## Phase 3E: manual upload kits

Convert an existing approved export bundle into platform-specific local files:

```powershell
python upload_kit.py --job-id <job_id> --export-root exports --platform all
python upload_kit.py --job-id <job_id> --export-root exports --platform youtube_shorts
python upload_kit.py --job-id <job_id> --export-root exports --platform tiktok
python upload_kit.py --job-id <job_id> --export-root exports --platform instagram_reels
```

Kits are written under `exports/upload_kits/<job_id>/` for YouTube Shorts,
TikTok, and Instagram Reels. Each platform receives the approved `final.mp4`,
available thumbnail/captions, deterministic metadata, capped hashtags, and a
practical human upload checklist.

Mission Control can create, refresh, and preview these local kits after an
approved export exists. Every kit is labeled **MANUAL UPLOAD ONLY - NOT
PUBLISHED**. Shorts Factory does not log in, call platform APIs, automate a
browser, upload files, or publish content; the final upload remains an
intentional human action.

## Phase 3F: local prompt/template editor

List, inspect, validate, and preview the built-in/local text templates:

```powershell
python template_editor.py --list
python template_editor.py --show script.default
python template_editor.py --validate script.default
python template_editor.py --preview script.default
```

Mission Control now includes a **Templates** page for viewing JSON templates,
validating edits, previewing against fixed sample data, saving versioned local
copies, browsing history, and restoring an earlier revision as a new version.
Editable copies live under `templates/`; generated history lives under
`templates/history/` and is ignored by Git.

Templates control script layout, caption/thumbnail text references, publisher
metadata, manual-upload checklist wording, and deterministic revision text.
Script generation, revision fallback text, and manual upload kits use a valid
local template when available and retain their existing deterministic behavior
when a template is missing or invalid. Job receipts record the selected script
template ID and hash; Mission Control shows recorded template provenance.

Templates are local, text-only JSON assets. Placeholder names are allowlisted;
expressions, filters, loops, HTML execution, Python, JavaScript, shell code,
dynamic imports, and path traversal are not supported. Template editing cannot
approve, export, upload, or publish a job.

## Phase 3G: local OS audit and demo dataset

Freeze the complete Phase 3 workflow into a reproducible local proof package:

```powershell
python phase3_audit.py --output-root output --export-root exports --demo-root demo_dataset
python phase3_audit.py --help
```

The audit proves:

```txt
Generate -> Score -> Review -> Revise -> Re-score -> Approve -> Export -> Manual Upload Kit -> Template Control
```

It writes the committed report to
`docs/audits/PHASE_3_LOCAL_OS_AUDIT.md` and a generated local dataset to
`demo_dataset/`. The dataset includes receipts, scripts, captions, revision and
quality evidence, approval/export manifests, all three manual upload kits, and
template validation/preview evidence.

Large media is detected and recorded in manifests but is not copied by default.
`demo_dataset/` is ignored by Git. Use `--copy-media` only when local media
copies are explicitly wanted. The audit never uploads or publishes anything;
its receipt always records live publishing disabled, no API upload attempt, and
manual upload only.

## Phase 4A: local desktop launcher

Open the safe terminal launcher from any working directory:

```powershell
python shorts_factory_launcher.py
python shorts_factory_launcher.py --help
python shorts_factory_launcher.py --health
```

The menu can start Mission Control on `127.0.0.1`, generate mock/API-mode local
shorts through the existing pipeline, score the latest receipt-backed job, run
the Phase 3 audit, print the key knowledge-document paths, print the latest
approved export/manual upload-kit folders, and run system health checks.

Non-interactive shortcuts are also available:

```powershell
python shorts_factory_launcher.py --start-mission-control
python shorts_factory_launcher.py --run-audit
python shorts_factory_launcher.py --generate-mock
python shorts_factory_launcher.py --generate-api
```

Health checks verify Python, ffmpeg, required imports, local roots, templates,
Git ignore safety, expected CLI files, and every core CLI help command. Optional
dependencies are reported as warnings. All child commands use argument lists,
`sys.executable`, absolute script paths, `shell=False`, and the repository as
their working directory, including on Windows paths containing spaces.

The launcher has no publishing, account connection, OAuth, cloud upload,
background scheduling, or platform-posting action. Manual upload kits remain
manual and Mission Control remains bound to localhost by default.

## Phase 4B: publisher-specific preview cards

Generate static local previews from an existing approved export/manual upload
kit:

```powershell
python preview_cards.py --job-id <approved_job_id> --export-root exports
python preview_cards.py --help
```

The command writes one escaped HTML card and one copy-friendly text preview for
YouTube Shorts, TikTok, and Instagram Reels, plus `PREVIEW_MANIFEST.json`, under:

```txt
exports/upload_kits/<job_id>/previews/
```

Each card shows the local video/thumbnail paths, title or caption, description
when supported, hashtags, checklist, character counts, local advisory warnings,
and all five manual-only safety flags. Advisory limits are offline constants,
not claims about current platform API validation.

Mission Control shows **Generate Preview Cards** after an approved manual upload
kit exists, then exposes local links for each platform card and manifest. All
user-controlled text is HTML-escaped; cards contain no remote JavaScript, CSS,
CDN, tracking, posting action, account connection, upload automation, or live
publishing capability.

## Phase 4C: final pre-publish compliance checklist

Add the last local human gate after preview cards are ready:

```powershell
python compliance_check.py --job-id <approved_job_id> --export-root exports
python compliance_check.py --job-id <approved_job_id> --export-root exports --mark-reviewed
python compliance_check.py --help
```

The command writes:

```txt
exports/upload_kits/<job_id>/compliance/COMPLIANCE_CHECKLIST.json
exports/upload_kits/<job_id>/compliance/COMPLIANCE_CHECKLIST.md
```

The checklist refuses to run unless all prerequisites already exist locally:
approved export bundle, upload kit, preview manifest, final video, receipt, and
the existing manual-only safety flags. It then records deterministic artifact
checks, advisory content/risk warnings, and required human review items.

Default status is always `needs_human_review` with
`ready_for_manual_upload: false`. Nothing becomes ready automatically. Only an
explicit local confirmation with `--mark-reviewed` changes the checklist to:

```json
"status": "ready_for_manual_upload",
"ready_for_manual_upload": true
```

Mission Control now shows **Generate Compliance Checklist**, **Open Compliance
Checklist**, and **Mark Reviewed for Manual Upload** on eligible job pages.
These actions reuse the same local checklist runner as the CLI. No platform API,
OAuth, account connection, upload automation, browser automation, or live
publishing is added.

The safety boundary remains explicit in every checklist:

```json
"manual_upload_only": true,
"publishing_status": "not_published",
"live_publishing_enabled": false,
"api_upload_attempted": false,
"requires_human_upload": true
```

## Phase 4D: manual results ledger

Record post-upload performance manually after a job is already marked ready for
manual upload:

```powershell
python results_ledger.py --job-id <ready_job_id> --platform youtube_shorts --url "https://example.com/manual-upload" --views 100 --likes 10 --notes "Manual upload test"
python results_ledger.py --list
python results_ledger.py --show <entry_id>
python results_ledger.py --summary
python results_ledger.py --update <entry_id> --views 250 --likes 25 --notes "Updated after 24 hours"
python results_ledger.py --help
```

The command writes local-only files under:

```txt
results_ledger/
  ledger.json
  entries/<entry_id>.json
  reports/RESULTS_SUMMARY.md
```

Entries are refused unless the job already has an approved export bundle,
manual upload kit, preview manifest, compliance checklist, and
`ready_for_manual_upload: true`. If compliance is still pending, run
`compliance_check.py` and mark the job reviewed first.

Each entry preserves these fixed safety fields:

```json
"manual_upload_only": true,
"api_fetch_attempted": false,
"api_upload_attempted": false,
"scraping_attempted": false,
"live_publishing_enabled": false
```

The URL is manually pasted and stored as plain local metadata only. Shorts
Factory does not open it, fetch it, scrape it, or validate it online. Metrics
are also manual local integers only: views, likes, comments, shares, saves, and
leads.

Mission Control now shows a **Results ledger** section on jobs whose compliance
status is already **Ready for Manual Upload**. From there you can **Record
Manual Result**, **Update Manual Result**, and **Open Results Summary**. No
Fetch/Sync/OAuth/account-connect/upload/publish behavior is added.

## Phase 4E: local performance review

Turn the manually entered results ledger into deterministic local decision
support:

```powershell
python performance_review.py --results-root results_ledger --output-root performance_reports
python performance_review.py --help
```

The command writes:

```txt
performance_reports/
  PERFORMANCE_REVIEW.md
  PERFORMANCE_REVIEW.json
  platform_summary.csv
  template_summary.csv
  job_summary.csv
```

The review computes totals and view-based like, comment, share, save, and lead
rates; ranks jobs deterministically by leads, views, likes, and oldest creation
time; summarizes platform and template signals; compares captured quality
scores; carries forward manual notes/lessons; and proposes one deterministic
next manual experiment. Zero-view entries produce zero rates. An absent or
empty ledger produces a complete empty-state report instead of failing.

Mission Control exposes the same local analysis at `/performance`, including
the current status, totals, best jobs, platform/template signals, recommendation,
Markdown path, and **Generate Performance Review** control.

Only local entries created by `results_ledger.py` are analyzed. The command does
not open stored URLs or use platform APIs, OAuth, automatic metric collection,
scraping, uploads, cloud services, or live publishing. JSON and Markdown reports
retain the explicit manual-only/no-fetch/no-upload/no-scraping/live-disabled
safety boundary. Generated `performance_reports/` remain local and ignored by
Git.

## Phase 4F: rich LIT verdict integration

LIT-GhostTown owns idea evaluation; Shorts Factory only validates and formats
the returned verdict. API-mode jobs can now consume the rich Phase 4F fields:

```txt
ghost_town_risk
buyer_pain_clarity
willingness_to_pay_signal
distribution_difficulty
unfair_advantage_check
business_model_weakness
why_it_might_work
why_it_might_fail
killer_question
mvp_test
```

Validated rich responses write `verdict_provenance` and `verdict_warnings` to
`receipt.json`. The same fields are stored in `verdict.json` and exposed as
text-only template placeholders. Existing templates remain valid.

Backward compatibility is deliberate: a complete legacy LIT verdict continues
with `rich_verdict: false` and an explicit warning. An invalid legacy verdict
still uses the existing deterministic `api_fallback` path. Mock mode remains
offline-safe. No paid AI key is required for tests.

The contract is documented in
`docs/contracts/LIT_VERDICT_CONTRACT.md`. This phase adds no publishing,
platform API, OAuth, scraping, metric collection, upload, or engagement
automation.

## Phase 5A: full autopilot dry-run pipeline

Run the automated machine path without credentials or live platform access:

```powershell
python autopilot.py run --mode dry_run --trend-query "hottest searched business ideas" --batch-size 3 --locale en-US
python autopilot.py list
python autopilot.py status --batch-id <batch_id>
python autopilot.py show --batch-id <batch_id>
python autopilot.py resume --batch-id <batch_id>
python autopilot.py next-plan --batch-id <batch_id>
```

The runner discovers deterministic mock or local-file trends, generates
business ideas, runs the existing LIT verdict boundary, rejects weak verdicts,
generates shorts, applies quality and compliance gates, simulates publishing
and analytics, reviews the simulated results, and writes the next batch
experiment. Every completed stage is written before the next begins under
`output/autopilot/batches/<batch_id>/`.

That directory includes the plan, selected trends, ideas, LIT verdicts,
accept/reject decisions, generated-job index, gate results, simulated publish
queue and attempts, simulated analytics, performance review,
`next_batch_plan.json`, and `AUTOPILOT_RECEIPT.json`. `resume` reuses those
receipts and continues from the first missing stage.

Provider contracts isolate trend intake, publisher adapters, and analytics
adapters. Phase 5A implements deterministic mock/file intake, a simulated
publisher, simulated/file analytics, and a refusing live-publisher adapter.
`supervised_autopilot` and `full_autopilot` are explicit placeholders and do
not create a live path.

Safety is fixed for Phase 5A: no live publishing, platform API upload, OAuth,
scraping, browser posting, credentials, or live analytics. Publish records and
metrics are simulated local artifacts only. Generated `output/` remains
ignored by Git.

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
