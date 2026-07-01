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

## Phase 5B: YouTube official publisher adapter boundary

Phase 5B adds a fail-closed `YouTubePublisherAdapter` without changing the
default Phase 5A runner. `dry_run` still uses only
`SimulatedPublisherAdapter`, never reads YouTube credentials, and never calls a
platform API.

The YouTube adapter validates the existing publisher plan and its
`youtube_shorts/metadata.json`, resolves the local video safely, and builds the
official `videos.insert` `snippet` and `status` body. Scheduled uploads accept
an ISO-8601 `schedule_window.publish_at`, require a future time, and force
`privacyStatus: private`, matching the official
[YouTube video resource rules](https://developers.google.com/youtube/v3/docs/videos).

Live preflight requires all of the following before the transport can run:

- `full_autopilot` mode at the adapter boundary
- `LIVE_PUBLISHING_ENABLED=true`
- `YOUTUBE_PUBLISHING_ENABLED=true`
- `AUTOPILOT_EMERGENCY_STOP=false`
- a non-expired OAuth access token with both
  `https://www.googleapis.com/auth/youtube.upload` and
  `https://www.googleapis.com/auth/youtube.readonly`
- `YOUTUBE_UPLOAD_QUOTA_REMAINING` of at least one
- `YOUTUBE_POLICY_ACKNOWLEDGED=true`
- top-level and YouTube metadata live opt-ins and approval
- explicit `made_for_kids`, valid privacy, title, description, tags, media,
  and optional schedule metadata

The official transport uses YouTube Data API
[`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert)
through optional `google-api-python-client` and `google-auth` packages. Those
packages and credentials are not required for tests or dry-run operation.
Google documents that upload requests require OAuth authorization, are quota
controlled, and may be restricted to private visibility for unaudited API
projects.

Every blocked, failed, or successful adapter attempt writes a redacted local
receipt under:

```txt
output/autopilot/batches/<batch_id>/publisher_receipts/youtube_shorts/<publish_attempt_id>.json
```

Tests use an injected fake transport. They exercise the successful adapter
path but do not publish a video or contact YouTube. TikTok, Instagram, OAuth
login UX, token refresh/storage, analytics, and production credential setup
remain out of scope.

## Phase 5B.1: YouTube credential bootstrap and preflight

Phase 5B.1 adds local installed-app OAuth setup without enabling uploads. Start
by installing the optional Google libraries:

```powershell
python -m pip install -r requirements-youtube.txt
python youtube_credentials.py dependencies
python youtube_credentials.py paths
```

In Google Cloud Console, enable the YouTube Data API and create an OAuth client
of type **Desktop app**. Download its JSON to the ignored local path shown by
`paths` (the default is `.local/youtube/client_secret.json`). Web-client and
service-account JSON are refused. Google documents that ordinary YouTube Data
API access uses user OAuth and that service accounts are not supported for this
upload use case: [YouTube OAuth guidance](https://developers.google.com/youtube/v3/guides/authentication).

Run the browser-based installed-app flow:

```powershell
python youtube_credentials.py bootstrap
```

The command requests exactly the two capabilities used by the current boundary:

- `https://www.googleapis.com/auth/youtube.upload` for the future upload adapter
- `https://www.googleapis.com/auth/youtube.readonly` for the preflight-only
  `channels.list(mine=true)` identity check

It requests offline access and saves the authorized-user token to
`.local/youtube/token.json`. Both local credential paths are covered by
`.gitignore`; neither secret is printed or written to a receipt.

Then validate the token and authenticated channel without uploading:

```powershell
python youtube_credentials.py preflight
python youtube_credentials.py preflight --confirm-quota-ready --confirm-policy-ready
```

Preflight refreshes an expired refreshable token, verifies both stored scopes,
reads channel title/id with `channels.list(mine=true)`, and writes:

```txt
output/youtube/credential_preflight/YOUTUBE_CREDENTIAL_PREFLIGHT.json
```

The confirmation flags record that the operator checked Google Cloud quota and
app/API policy readiness. They do not enable publishing. The receipt always
states `videos_insert_called: false`; `full_autopilot` and
`supervised_autopilot` remain closed. The environment-driven YouTube adapter
also requires this passed, confirmed receipt in addition to its existing live
gates.

Tokens created before the readonly-scope correction must be recreated:

```powershell
Remove-Item ".local\youtube\token.json"
python youtube_credentials.py bootstrap
python youtube_credentials.py preflight
```

The bootstrap prompt will request upload plus readonly access. Preflight still
does not upload or call `videos.insert`.

## Phase 5B.2: supervised first YouTube upload gate

Phase 5B.2 adds one deliberately separate live path for exactly one
human-selected, human-approved YouTube video. It does not run through the Phase
5A batch runner, does not enable `supervised_autopilot` or `full_autopilot`, and
does not change `dry_run`. The normal autopilot runner still uses only
`SimulatedPublisherAdapter`.

The command defaults to refusal. Hector must invoke it manually with one video,
the generated YouTube metadata referenced by that job's publisher plan, the
exact Ghost Town Test channel ID, and all three approval flags:

```powershell
python youtube_supervised_upload.py `
  --video "output/jobs/<job_id>/short.mp4" `
  --metadata "output/jobs/<job_id>/publish/youtube_shorts/metadata.json" `
  --confirm-channel-id UCIzMYpBt3WdSXZBrvoE7eCg `
  --confirm-live-upload `
  --confirm-quota-reviewed `
  --confirm-policy-reviewed
```

Before loading runtime credentials or calling the injected YouTube transport,
the gate requires:

- a passed, redacted Phase 5B.1 preflight receipt with both scopes and verified
  channel identity
- preflight evidence that no upload, `videos.insert`, or secret recording has
  occurred
- exact channel confirmation for `UCIzMYpBt3WdSXZBrvoE7eCg` (`Ghost Town Test`)
- exactly one non-empty video file, with directories and batch selection refused
- the video listed in its generation `receipt.json`
- exactly one completed Phase 5A `dry_run` batch containing that generated job
- matching complete LIT verdict, passing quality gate, and passing compliance gate
- the generated YouTube metadata file referenced by the same publisher plan
- a non-empty title and description, explicit valid `privacy_status`, explicit
  `made_for_kids`, and private visibility for scheduled publishing
- all three live, quota, and policy approval flags on the current command

The generated dry-run metadata remains non-live. Phase 5B.2 treats the CLI
approval flags as the live authorization and never rewrites the dry-run plan.
If the selected generated metadata does not yet contain explicit
`privacy_status` and `made_for_kids` values, the command refuses before reading
credentials or calling YouTube.

Each invocation creates a unique directory under:

```txt
output/youtube/supervised_uploads/<attempt_id>/
```

Blocked runs write one immutable `01_blocked_*.json` receipt. A transport-bound
run writes `01_attempted_live_upload.json` before the call, followed by a
separate `02_successful_live_upload.json` or `02_failed_live_upload.json`.
Receipts contain channel, selected artifact, metadata summary, source receipt
references, and gate results, but never tokens, secrets, or authentication URLs.
Tests inject a fake transport and make no real network calls. No real upload is
performed by setup, tests, dry-run, or documentation commands.

## Phase 5B.3: YouTube metadata hardening

The first manual supervised upload succeeded on `Ghost Town Test` as video
[`rnPTrNn2bgc`](https://www.youtube.com/watch?v=rnPTrNn2bgc). Phase 5B.3
removes the manual JSON patching that was needed before that upload. It adds the
versioned `youtube_upload_metadata.v1` contract and a composer that rewrites the
publisher-plan-owned metadata as valid UTF-8 JSON without a BOM. It does not
upload, read credentials, or enable either autopilot live mode.

Harden one generated job before each future supervised upload:

```powershell
python youtube_metadata.py harden `
  --job-id <job_id> `
  --privacy-status private `
  --made-for-kids false `
  --brand-name "Ghost Town Test" `
  --website-url "" `
  --cta-text "Follow Ghost Town Test for more business idea tests."
```

The command finds `output/jobs/<job_id>/receipt.json`, follows that job's
`publish/publisher_plan.json` to the original generated YouTube metadata, and
verifies that its video is listed by the generation receipt. It preserves the
generated title, description, caption, hashtags, video, thumbnail, and captions;
then it adds:

- `schema_version: youtube_upload_metadata.v1`
- `privacy_status`, defaulting to `private`
- explicit `made_for_kids`, defaulting to `false`
- clean YouTube `tags` without `#`, including the canonical Ghost Town Test tags
- safe category `22` when no category is present
- source receipt references and generation timestamp
- optional validated public website and CTA text, appended only to the description

Websites must use public `http` or `https` URLs without credentials,
authentication endpoints, or token-like query parameters. Metadata containing
secrets or authentication URLs is refused. Scheduled `publish_at` metadata is
valid only with private visibility. Hashtags remain separate and retain `#`.

Each successful hardening writes:

```txt
output/youtube/metadata_hardening/<job_id>/<timestamp>_YOUTUBE_METADATA_HARDENING.json
```

The receipt records the previous/new SHA-256 hashes, upload settings, tags,
website/CTA inclusion, source receipts, and UTF-8-without-BOM verification. The
CLI then prints the exact `youtube_supervised_upload.py` command for that job.
Manual JSON editing and sidecar metadata are unnecessary; a sidecar remains
refused unless the trusted publisher plan explicitly references it.

The supervised uploader accepts schema-valid V1 metadata or a complete legacy
record that can be safely upgraded in memory. Missing hardening fields, invalid
JSON, or a BOM are refused with a command telling the operator to run
`youtube_metadata.py harden`. Upload receipts record the metadata schema version.

## Phase 5B.4: upload verification and analytics snapshots

Phase 5B.4 closes the read-only measurement loop after a successful supervised
upload. It adds a durable upload index, explicit `videos.list` verification,
and two independent YouTube Analytics reports. It cannot publish, never calls
`videos.insert`, does not run from the batch autopilot, and does not enable
`supervised_autopilot` or `full_autopilot`.

Rebuild or inspect the local upload index:

```powershell
python youtube_upload_index.py rebuild
python youtube_upload_index.py show
```

The idempotent index scans successful supervised-upload receipts and writes:

```txt
output/youtube/uploads/YOUTUBE_UPLOAD_INDEX.json
```

It maps YouTube video IDs back to attempt, job, video, V1 metadata, hardening,
credential-preflight, verification, and analytics receipts. Rebuilds preserve
the latest verification and analytics pointers.

Verify one indexed upload through the YouTube Data API read-only
`videos.list` endpoint:

```powershell
python youtube_verify_upload.py `
  --video-id sa1FZFgUgIQ `
  --expected-channel-id UCIzMYpBt3WdSXZBrvoE7eCg
```

or use its successful upload receipt:

```powershell
python youtube_verify_upload.py `
  --from-success-receipt "output/youtube/supervised_uploads/<attempt_id>/02_successful_live_upload.json" `
  --expected-channel-id UCIzMYpBt3WdSXZBrvoE7eCg
```

Verification requires the passed credential preflight, exact Ghost Town Test
channel identity, and runtime readonly credentials before calling
`videos.list`. It writes an immutable receipt under:

```txt
output/youtube/verifications/<video_id>/<timestamp>_YOUTUBE_UPLOAD_VERIFICATION.json
```

YouTube Analytics requires the optional
`https://www.googleapis.com/auth/yt-analytics.readonly` scope. Existing upload
and verification preflight remains valid without it. To explicitly replace the
local token with one that also requests analytics, run the browser bootstrap
and then refresh the preflight receipt:

```powershell
python youtube_credentials.py bootstrap --include-analytics-scope
python youtube_credentials.py preflight
```

The analytics command is explicit and read-only:

```powershell
python youtube_analytics_snapshot.py --video-id sa1FZFgUgIQ --days 1
```

Every invocation writes two separate receipts:

```txt
output/youtube/analytics/<video_id>/<timestamp>_YOUTUBE_ANALYTICS_SNAPSHOT.json
output/youtube/analytics/<video_id>/<timestamp>_YOUTUBE_COUNTRY_ANALYTICS_SNAPSHOT.json
```

The default video-performance report requests:

- `views`
- `estimatedMinutesWatched`
- `averageViewDuration`
- `likes`
- `comments`
- `shares`

The country report uses dimension `country`; requests `views`,
`estimatedMinutesWatched`, `averageViewDuration`, and `likes`; sorts by
`-views`; and caps results at 25. Each report runs independently. If YouTube
rejects a metric/dimension combination, only that receipt records
`snapshot_status: blocked_or_unsupported` with a redacted reason; the sibling
report still runs and the command does not invoke any upload API. New or private
videos may legitimately produce `empty` receipts.

## Phase 5B.5: online-capable creative angle packs

Turn one stored trending idea and its LIT verdict into five distinct short-form
creative experiments plus one long-form YouTube assembly plan:

```powershell
python creative_angle_pack.py generate `
  --idea-id <idea_id> `
  --provider deterministic
```

The deterministic provider is the default. It uses no credentials or network,
and writes a gated pack under `output/creative_angle_packs/<angle_pack_id>/`.
Each pack contains `creative_angle_pack.json`, five angle-specific job/script/
caption/thumbnail packages, analytics mapping placeholders, a long-form plan
and script, and `ANGLE_PACK_RECEIPT.json`.

Checked-in LIT verdict and creative-output fixtures exercise regression behavior
without a network call:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider fixture
```

Online generation is optional and must be selected explicitly. Phase 5B.5A
resolves the selected model through the model registry instead of hardcoding a
provider. Inspect the safe example profiles and validate optional ignored local
overrides:

```powershell
python llm_models.py list
python llm_models.py show --model fake-json-model
python llm_models.py validate-config
python llm_models.py test --model fake-json-model --dry-run
```

Local model profiles belong in `.local/llm/models.json`, which is ignored by
Git. Safe examples live in `config/examples/llm_models.example.json`. Profiles
contain capabilities, context/output limits, optional pricing, latency class,
recommended tasks, and safety notes—but never credentials. Generic HTTP adapter
credentials remain environment-only using provider-specific
`LLM_<PROVIDER>_API_URL` and `LLM_<PROVIDER>_API_KEY` names.

Switch models with `--model`:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model <model_id>
```

The checked-in `fake-json-model` exercises the complete online-provider path
offline:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model fake-json-model
```

The online adapter requests structured JSON only. It stores validated output,
hashes, token/cost summaries when supplied, and redacted receipts—never API
keys, prompts containing detected secrets, or raw provider responses. Missing,
disabled, or schema-incapable model profiles refuse before generation. Missing
generic-provider credentials refuse before a network call. Invalid JSON,
invalid schemas, or failed quality gates write a blocked receipt without
creating short or long-form artifacts. `llm_models.py test` cannot call a live
provider unless `--confirm-live-llm-call` is passed explicitly.

Every provider remains subordinate to orchestration and gates. The five required
angles are `ghost_town_risk`, `buyer_reality`, `fast_validation_test`,
`contrarian_opportunity`, and `builder_action_plan`. Metadata stays
`draft_not_upload_ready`; analytics fields remain null/pending until separately
mapped to existing offline receipts. Creative generation does not publish,
collect analytics, or change Phase 5A `dry_run`. Both `supervised_autopilot` and
`full_autopilot` remain refused. See
`docs/architecture/CREATIVE_ANGLE_PACKS.md` and
`docs/architecture/ONLINE_LLM_GENERATION_PROVIDER.md`.

### Phase 5B.5B: first real online creative generation

Create the ignored local real-model profile template:

```powershell
python llm_models.py init-local-config
```

The command refuses to overwrite `.local/llm/models.json` unless `--force` is
passed, verifies that Git ignores the target, and writes environment-variable
names—not credentials. Edit the profile’s model identity/capabilities if needed,
then set its configured `LLM_API_KEY` and `LLM_BASE_URL` environment variables.
Never place their values in the profile, `.env` under version control, command
arguments, or receipts.

Validate locally before an online attempt:

```powershell
python llm_models.py validate-config
python llm_models.py show --model real-creative-model
```

Then explicitly generate one real candidate pack:

```powershell
python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model real-creative-model
```

The adapter makes one structured creative-bundle request containing the stable
prompt prefix, one LIT verdict, five-angle contract, brand/audience context, and
output schema. It requests five shorts and one long-form plan together. Invalid
JSON/schema, secrets, unsupported claims, publishing instructions, or YouTube
API instructions fail closed. Every online attempt writes a redacted receipt;
accepted artifacts use status `passed`, while preflight/schema failures are
`blocked` and transport-bound failures are `failed`.

Compare a deterministic pack with an accepted online pack entirely offline:

```powershell
python creative_angle_pack.py compare `
  --left output/creative_angle_packs/<deterministic_pack_id>/creative_angle_pack.json `
  --right output/creative_angle_packs/<online_pack_id>/creative_angle_pack.json
```

The comparison receipt covers hooks, titles, thumbnail text, CTA, script
specificity, angle uniqueness, long-form completeness, and source quality gates.
Generation and comparison never publish or call YouTube APIs; both autopilot
live modes remain closed.

### Free/open-source model routes

OpenRouter is the first recommended cloud provider. The default creative route
is the ordered `openrouter-free-creative-chain`, not the automatic free router.
Register with
OpenRouter and create a new key; revoke any key previously pasted into chat or
otherwise exposed. Keep the key only in the current PowerShell session or an
ignored environment file, with optional attribution headers:

```powershell
$env:OPENROUTER_API_KEY="<key>"
$env:OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
$env:OPENROUTER_HTTP_REFERER="https://ghosttowntest.com" # optional
$env:OPENROUTER_APP_TITLE="Ghost Town Test"              # optional

python llm_models.py list-fallbacks
python llm_models.py show-fallback --fallback-group openrouter-free-creative-chain
python llm_models.py test-fallback --fallback-group openrouter-free-creative-chain --dry-run

python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --fallback-group openrouter-free-creative-chain
```

`ollama-local` is the preferred no-cloud route and needs no API key:

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434/v1"

python creative_angle_pack.py generate `
  --lit-verdict-file fixtures/lit_verdicts/sample.json `
  --provider online_llm `
  --model ollama-local
```

Inspect both profiles without a network call:

```powershell
python llm_models.py show --model openrouter-gemma-4-26b-free
python llm_models.py show --model ollama-local
python llm_models.py test-fallback --fallback-group openrouter-free-creative-chain --dry-run
python llm_models.py test --model ollama-local --dry-run
```

The chain tries four explicit `:free` creative model slugs before
`openrouter/free`. The automatic router is last because it can choose an
unsuitable safety or moderation model. Exact slugs are ordinary profiles and
can be corrected in ignored `.local/llm/models.json` if OpenRouter changes
availability. Prefer `:free` to avoid accidental paid usage. BytePlus ModelArk
and user-provided or self-hosted HTTPS endpoints remain future profiles.

Each attempt is one non-streaming strict-JSON request. `reasoning.enabled` is
never sent, and raw responses and `reasoning_details` are never stored.

Free routes may be rate-limited or unavailable, and free/open models may have
weaker JSON reliability. All output still must pass strict local schema and
quality gates. Remote HTTP is refused; loopback HTTP is allowed only for the
explicit local profile. Hugging Face is documented as an optional reviewed
generic OpenAI-compatible profile, not enabled as a built-in route. LLM output
never publishes, and API keys remain environment-only.

## Rules

Do not activate unsupervised live publishing or add TikTok, Instagram, real
trend scraping, or G20 scaling without a separately approved phase and green
gate. The Phase 5B.2 command remains the only approved supervised upload
boundary; Phase 5B.3 only composes and validates metadata.

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
