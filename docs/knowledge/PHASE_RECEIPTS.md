# Phase Receipts

## Phase 1 / MVP — Local Mock Pipeline

Status: complete

Outputs:
- `script.txt`
- `captions.srt`
- `thumbnail.jpg`
- `short.mp4`
- `receipt.json`

Result:
The repo can generate one local mock short end-to-end.

## Phase 2A — LIT API Connection

Status: complete

Commit:
`2ad9b80 Implement Phase 2A LIT API integration`

Implemented:
- Real LIT HTTP client
- Configurable URL and timeout
- Optional Bearer authentication
- Response normalization
- Strict verdict validation
- Safe API fallback
- `lit_api_response.json` on successful API calls
- Tests and README instructions

Known note:
The exact LIT-side companion commit is not recorded here. If needed, check the LIT-GhostTown repo separately.

## Phase 2B — Controlled Playwright Recording

Status: complete

Commit:
Not visible in the provided `git log -10`; verify and fill if needed.

Implemented:
- Controlled Playwright recorder
- `--record-app` CLI flag
- Raw WebM recording
- Normalized MP4 recording
- Final screenshot
- Receipt recording metadata
- Tests

Evidence reported:
- First-win command succeeded.
- WebM and H.264 MP4 verified at 1080×1920.
- Mock and API modes remain recording-disabled by default.
- No real-user recording added.

## Phase 2C — Real Voiceover/TTS

Status: complete

Commit:
`bd8d3e3 Add Phase 2C voiceover generation`

Evidence:
- 23 tests passed
- Real SAPI voiceover
- 25.216s PCM WAV
- Final MP4 includes AAC audio
- Final MP4 H.264 1080×1920

## Phase 2D — Background Music Mixing

Status: complete

Commit:
`b2a1759 Add Phase 2D background music mixing`

Evidence:
- 27 tests passed
- Final MP4 H.264 1080×1920 with AAC audio
- Voice retention correlation: 0.997021

## Phase 2E — Real Localization

Status: complete

Commit:
`53a2b4f Add Phase 2E localization support`

Implemented:
- Deterministic en-US / es-PR localization
- One localized verdict feeds every renderer
- Fallback warning for unsupported locales
- No translation service or LLM dependency

## Phase 2F — Local Queue and Scheduler

Status: complete

Commit:
`a3edbba Add Phase 2F local queue and scheduler`

Implemented:
- Local queue
- Local scheduler
- Single-process queue constraints documented

## Phase 2G — Dry-Run Publisher Packages

Status: complete

Commit:
`48fb757 Add Phase 2G dry-run publisher packages`

Evidence:
- 44 tests passed
- Final media: H.264/AAC, 1080×1920
- Live publishing disabled and explicitly refused
- Publisher packages require human approval

Reported receipt:
`output/phase2g-acceptance/jobs/2b600930dc05/receipt.json`

## Phase 3A — Local Mission Control

Status: complete

Commit:
`Add Phase 3A local mission control dashboard`

Implemented:
- Standard-library local HTTP dashboard bound to `127.0.0.1` by default
- Receipt-backed job index for normal output and Phase 2G acceptance output
- Safe previews for video, thumbnail, script, captions, receipt, warnings, and
  publisher package data
- Dry-run publisher package labeling
- Local pending / approved / rejected / needs-revision JSON approval records
- Allowlisted artifact serving with resolved-path containment checks
- HTML escaping for generated text and JSON

Evidence:
- `pytest -q`: 56 passed
- `python mission_control.py --help`: passed
- Exact first-win server command started at `http://127.0.0.1:8765`
- Existing job `2b600930dc05` appeared and its detail page returned 200
- Thumbnail served as JPEG and generated video preview was present
- `publish/publisher_plan.json` appeared with `DRY RUN ONLY — NOT PUBLISHED`
- Approval was written under `output/approvals/2b600930dc05.json`
- Encoded path traversal smoke request returned 404
- No live publishing or external integration was added

## Phase 3B — Approval-Gated Local Export Bundles

Status: complete

Commit:
`Add Phase 3B approval-gated export bundles`

Implemented:
- `export_bundle.py` local CLI with clear non-zero refusal behavior
- Strict local `approved` state requirement using the original approval record
- Final-video selection priority and normalized `final.mp4` output
- Deterministic replacement at `exports/approved/<job_id>/`
- Required receipt and approval snapshots plus all available supporting assets
- `EXPORT_MANIFEST.json` with missing optional files and source/export paths
- Mandatory `publishing_status: not_published` and
  `live_publishing_enabled: false` manifest fields
- Minimal Mission Control local export POST action, status, and manifest preview
- Resolved-path containment checks for source and destination paths

Evidence:
- Baseline `pytest -q`: 56 passed
- Final `pytest -q`: 74 passed
- Both CLI help commands passed
- Pending real job `2b600930dc05` was refused with exit code 1
- Mission Control approved and exported that job through local POST actions
- Exact first-win CLI exported successfully and was idempotent
- Export contained `final.mp4`, receipt, approval, manifest, thumbnail, captions,
  script, publisher package, app recording assets, and LIT response
- Exported video hash matched the preferred music-mixed source
- Manifest recorded not published and live publishing disabled
- Generated export was confirmed ignored by Git
- No platform API, OAuth, cloud upload, scraping, or live publishing was added

## Phase 3C — Human Revision Queue

Status: complete

Commit:
`Add Phase 3C human revision queue`

Implemented:
- Separate local revision tasks under `output/revisions/<job_id>.json`
- Queued, complete, and failed revision states with attempts and warnings
- Deterministic hook, CTA, shortening, locale-preservation, and fallback rules
- New normal revised jobs under `output/jobs/<revised_job_id>/`
- Regenerated script, captions, thumbnail, and basic local MP4
- Revision receipt lineage and `REVISION_MANIFEST.json`
- Mandatory reapproval, not-published, and live-publishing-disabled flags
- Original artifact preservation and deterministic revised job IDs
- Minimal Mission Control task/run/status/revised-link/lineage controls
- Phase 3B export refusal until the revised job is separately approved

Evidence:
- Baseline `pytest -q`: 74 passed
- Focused Phase 3C and regression groups: 43 passed
- Final `pytest -q`: 87 passed
- All three required CLI help commands passed
- Mission Control created a real revision task for job `2b600930dc05`
- Exact revision CLI created `2b600930dc05-r90e9c5450d`
- All six required revised-job artifacts were present
- Hash comparison confirmed every original job file was unchanged
- Revised approval file was absent and read as pending
- Export refused the revised job before separate approval
- Mission Control displayed the original-job link and Requires reapproval state
- Separate approval allowed export, whose manifest remained not published
- Revision tasks, revised jobs, and exports were confirmed ignored by Git
- No LLM, TTS, Playwright, platform API, upload, scraping, or publishing was added
