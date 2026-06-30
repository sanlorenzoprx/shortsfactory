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

## Phase 3D — Deterministic Local Quality Scoring Dashboard

Status: complete

Commit:
`Add Phase 3D quality scoring dashboard`

Implemented:
- `score_job.py` local scoring CLI and optional JSON output
- Atomic reports under `output/quality/<job_id>.json`
- Nine deterministic weighted categories: hook, clarity, CTA, captions, media,
  audio, localization, receipt, and publisher package
- Pass/warn/fail thresholds with actionable issue and suggested-fix records
- Approval/export readiness derived without mutating either workflow
- Mandatory not-published and live-publishing-disabled report fields
- Mission Control score/re-score POST, index status, category scores, issues,
  fixes, recommended action, and readiness display
- Path containment, safe report validation, and HTML escaping

Evidence:
- Baseline `pytest -q`: 87 passed
- Focused Phase 3D tests: 16 passed
- Final `pytest -q`: 103 passed
- All four required CLI help commands passed
- Exact score CLI wrote real original and revised quality reports
- Original job scored 100/pass but respected its needs-revision human state
- Revised job scored 97/pass and reported export-ready only because separately approved
- Re-scoring through Mission Control returned 303 and updated the dashboard
- Approval, export, and job artifact hashes remained unchanged by scoring
- Generated reports were confirmed ignored by Git
- No approval, export, revision, platform, cloud, LLM, or publishing action was triggered

## Phase 3E — Manual Upload Checklists and Platform Formatting

Status: complete

Commit:
`Add Phase 3E manual upload kits`

Implemented:
- `upload_kit.py` local CLI for one platform or all supported platforms
- Strict source validation limited to sealed `exports/approved/<job_id>/`
- YouTube Shorts title/description, TikTok caption, and Instagram Reels caption
- Deterministic capped hashtags and exact platform-specific manual checklists
- Per-platform metadata plus root `UPLOAD_KIT_MANIFEST.json`
- Five mandatory manual-only/not-published/no-API safety fields
- Optional thumbnail/caption copying with missing-file records
- Idempotent per-platform replacement without deleting sibling kits
- Mission Control create/refresh action and escaped manifest/metadata/checklist previews
- Explicit absence of any live Publish button

Evidence:
- Baseline `pytest -q`: 103 passed
- Focused Phase 3E tests: 18 passed
- Final `pytest -q`: 121 passed
- All five required CLI help commands passed
- Exact first-win command created all three real platform kits
- Final MP4 copies matched the sealed approved export by hash
- YouTube title length was 23; hashtag counts were 8, 6, and 9 within caps
- All platform and root manifests contained all five safety fields
- Source export hashes remained unchanged
- Mission Control displayed all platform metadata/checklist previews
- No live Publish button appeared
- Generated upload kits were confirmed ignored by Git
- No platform API, OAuth, browser login, upload, cloud, scraping, or publishing was added

## Phase 3F — Local Prompt/Template Editor

Status: complete

Commit:
`Add Phase 3F local template editor`

Implemented:
- Text-only JSON template model for scripts, captions, thumbnails, publisher
  metadata, upload checklists, revisions, and quality messages
- Built-in local defaults plus editable copies under `templates/`
- Strict template ID, schema, placeholder, expression, and path validation
- Deterministic SHA-256 template hashes and replacement-only rendering
- Atomic saves with monotonic versions, ignored history, and validated restore
- Locked-template overwrite refusal
- `template_editor.py` list, show, validate, and fixed-context preview commands
- Mission Control template list/detail, escaped JSON editor, validate, save,
  history, restore, and preview routes
- ScriptWriter template use with unchanged deterministic fallback
- Receipt template ID/hash/source provenance and Mission Control display
- Upload-kit publisher metadata/checklist templates with safe fallback
- Revision text templates with safe fallback and lineage preservation

Evidence:
- Baseline `pytest -q`: 121 passed
- Focused Phase 3F tests: 25 passed
- Final `pytest -q`: 146 passed in 58.84s
- All four first-win template CLI commands passed
- Template, Mission Control, upload-kit, score, export, and revision help passed
- Exact Mission Control start command served jobs and templates on 127.0.0.1
- Templates page returned 200, listed `script.default`, and had no Publish button
- Real generated job `cedefcd5ec72` recorded `script.default` and its SHA-256 hash
- Invalid/forbidden placeholders and path traversal were refused
- HTML/script template text rendered escaped in Mission Control
- Template code-like text remained inert plain text in deterministic tests
- Generated output and template history remained ignored by Git
- No network, platform API, OAuth, browser login, cloud upload, scraping,
  external database, paid API, LLM, remote marketplace, or live publishing was added

## Maintenance — Mission Control Revision Route

Status: complete

Commit:
`Fix Mission Control revision route`

Implemented:
- Preserved the existing direct Python call to the deterministic revision runner
- Redirected a successful run to the returned revised job ID instead of the original
- Preserved safe HTTP 409 error rendering for refused/failed revisions
- Left the revision engine, other Mission Control pages, and publishing gates unchanged

Evidence:
- Route test passed with output, export, and template roots containing spaces
- Revised job contained `REVISION_MANIFEST.json`
- Original source artifact hashes remained unchanged
- Revised job remained pending and required separate reapproval
- Real job `f1632efa9488` returned HTTP 303 to
  `/jobs/f1632efa9488-r356e819a9d`
- Final `pytest -q`: 148 passed in 76.94s
- Mission Control and revision CLI help commands passed

## Phase 3G — Phase 3 Audit Report and Demo Dataset

Status: complete

Commit:
`Add Phase 3G audit report and demo dataset`

Implemented:
- `phase3_audit.py` local audit CLI with optional JSON, existing-pair, and
  explicit media-copy modes
- In-process reuse of generation, scoring, Mission Control rendering, revision,
  approval, export, manual upload-kit, and template-control paths
- Dedicated stable audit job that avoids mutating unrelated jobs by default
- Complete ignored `demo_dataset/` with original/revised job evidence, quality
  reports, approval/export manifests, all platform kit text/JSON, and templates
- Media detection/size manifests with no media copying by default
- Explicit `--copy-media` behavior for intentional local media copies
- `audit_receipt.json` proving all nine flow steps and six safety constraints
- Committed `docs/audits/PHASE_3_LOCAL_OS_AUDIT.md`
- Configured-root containment and path traversal refusal

Evidence:
- Baseline `pytest -q`: 148 passed
- Focused Phase 3G tests: 5 passed
- Final `pytest -q`: 153 passed in 74.16s
- Exact first-win audit command passed
- Audit generated/reused `phase3-audit-original` and a linked revised job
- Original and revised quality reports, revision manifest, approval snapshot,
  export manifest, upload-kit manifest, and template evidence were inspected
- All nine `flow_verified` fields were true
- `live_publishing_enabled: false`
- `api_upload_attempted: false`
- `manual_upload_only: true`
- No media appeared under the default demo dataset
- `demo_dataset/` was confirmed ignored by Git
- No live publishing, platform API, OAuth, cloud upload, scraping, real-user
  recording, external database, paid API, LLM dependency, or Phase 4 work was added

## Phase 4A — Local Desktop Launcher

Status: complete

Commit:
`Add Phase 4A local desktop launcher`

Implemented:
- `shorts_factory_launcher.py` interactive menu and non-interactive shortcuts
- Mission Control start command fixed to `127.0.0.1`
- Existing mock/API generation, latest-job scoring, and Phase 3 audit commands
- Knowledge-document and latest export/upload-kit path discovery
- Local health report for Python, ffmpeg, imports, roots, Git ignore status,
  templates, CLI files, and seven CLI help commands
- Safe subprocess list arguments using `sys.executable`, absolute script paths,
  repository working directory, and `shell=False`
- Clean EOF, Ctrl+C, missing-job, process-error, and nonzero-exit handling

Evidence:
- Baseline `pytest -q`: 153 passed
- Focused Phase 4A tests: 10 passed
- Final `pytest -q`: 163 passed in 96.84s
- `python shorts_factory_launcher.py --help`: passed
- `python shorts_factory_launcher.py --health`: passed with only an optional
  `python-dotenv` warning
- Interactive menu rendered all nine required options and exited cleanly
- Launcher-driven Phase 3 audit passed with all publishing safety flags intact
- Mission Control command used an absolute path containing spaces and explicit
  `--host 127.0.0.1`
- No posting, OAuth, account-connect, timer, cloud, platform API, scraping,
  real-user recording, external database, or Phase 4B behavior was added

## Phase 4B — Publisher-Specific Preview Cards

Status: complete

Commit:
`Add Phase 4B publisher preview cards`

Implemented:
- `preview_cards.py` local CLI for approved all-platform manual upload kits
- Strict approved export, final media, upload-kit, per-platform metadata, and
  five-flag safety validation before rendering
- Static escaped HTML and copy-friendly text cards for YouTube Shorts, TikTok,
  and Instagram Reels
- Offline advisory title/caption/description/hashtag rules labeled
  `local_advisory_warning`
- Deterministic preview manifest with source paths, platform files, warnings,
  manual-review status, and all safety flags
- Atomic local preview-directory replacement with path containment checks
- Mission Control preview generation, status/links, allowlisted file serving,
  nosniff headers, and restrictive local content security policy

Evidence:
- Baseline `pytest -q`: 163 passed
- Focused Phase 4B tests: 9 passed
- Final `pytest -q`: 172 passed in 82.15s
- Exact first-win command passed for approved job
  `phase3-audit-original-re054436d34`
- Seven required preview files were generated and inspected
- Manifest recorded all three platforms ready and all five safety flags
- HTML/text scans found no remote script, URL, button, tracker, or posting action
- Script-tag content was escaped in unit and Mission Control HTTP tests
- Mission Control showed all platform/manifest links and served preview HTML
- Unsafe flags, missing kits, and non-approved exports were refused
- No platform API, OAuth, browser automation, upload, cloud, scraping,
  real-user recording, external database, paid dependency, or Phase 4C work was added

## Phase 4C â€” Final Pre-Publish Compliance Checklist

Status: complete

Commit:
`Add Phase 4C final compliance checklist`

Implemented:
- `compliance_check.py` local CLI for deterministic compliance generation and
  explicit local mark-reviewed confirmation
- Strict approved-export, upload-kit, preview-manifest, preview-file, final
  video, receipt, and five-flag safety validation before writing output
- Local JSON and Markdown checklist artifacts under
  `exports/upload_kits/<job_id>/compliance/`
- Deterministic artifact checks plus advisory placeholder, risky-wording, and
  local platform copy checks without any LLM or moderation API
- Default `needs_human_review` and `ready_for_manual_upload: false`
- Explicit `ready_for_manual_upload` only after human review confirmation
- Mission Control compliance generate/open/refresh/mark-reviewed controls and
  allowlisted static file serving
- Escaped Mission Control warning rendering and safe HTTP 409 refusal pages

Evidence:
- Baseline `pytest -q`: 172 passed
- Focused Phase 4C tests: 13 passed
- Final `pytest -q`: 185 passed in 94.09s
- `python compliance_check.py --help`: passed
- `python compliance_check.py --job-id phase3-audit-original-re054436d34 --export-root exports`: passed
- `python compliance_check.py --job-id phase3-audit-original-re054436d34 --export-root exports --mark-reviewed`: passed
- `python preview_cards.py --help`: passed
- `python shorts_factory_launcher.py --health`: passed with the existing optional
  `dotenv` warning only
- `python mission_control.py --help`: passed
- `python upload_kit.py --help`: passed
- `python phase3_audit.py --help`: passed
- Generated checklist status begins at `needs_human_review`
- Generated reviewed checklist records `review_method` and `reviewed_at`
- Compliance output retains all five manual-only/not-published safety flags
- Real JSON and Markdown checklist files were inspected under
  `exports/upload_kits/phase3-audit-original-re054436d34/compliance/`
- Mission Control localhost smoke re-generated the checklist, showed Needs Human
  Review, marked it reviewed, then showed Ready for Manual Upload
- Mission Control showed compliance controls without any Publish/Post/OAuth
  button or automatic upload path
- No platform API, OAuth, browser automation, upload, cloud, scraping,
  external database, paid dependency, or Phase 4D work was added

## Phase 4D â€” Manual Results Ledger

Status: complete

Commit:
`Add Phase 4D manual results ledger`

Implemented:
- `results_ledger.py` local CLI for manual result creation, list, show, update,
  and summary output
- `content_factory.results` validation/store/report stack for local ledger JSON,
  per-entry JSON, and markdown summary generation
- Strict approved-export, upload-kit, preview-manifest, and compliance-ready
  prerequisite checks before recording any result
- HTTPS-only manual URL validation with no online fetch, crawl, or scraping
- Non-negative integer metrics for views, likes, comments, shares, saves, and leads
- Context capture for quality score/status, compliance status, and template
  provenance when those artifacts exist locally
- Mission Control results section, create/update form, entry display, and
  summary/entry links with safe local error rendering
- `results_ledger/` ignored by Git

Evidence:
- Baseline `pytest -q`: 185 passed
- Focused Phase 4D tests: 10 passed
- Final `pytest -q`: 195 passed in 96.74s
- `python results_ledger.py --help`: passed
- `python results_ledger.py --list`: passed before and after creating a real entry
- `python results_ledger.py --summary`: passed before and after creating a real entry
- `python results_ledger.py --job-id phase3-audit-original-re054436d34 --platform youtube_shorts --url "https://example.com/manual-upload" --views 100 --likes 10 --notes "Manual upload test"`: passed
- `python shorts_factory_launcher.py --health`: passed with the existing optional
  `dotenv` warning only
- `python compliance_check.py --help`: passed
- `python preview_cards.py --help`: passed
- `python mission_control.py --help`: passed
- Result entries require compliance `ready_for_manual_upload: true`
- Ledger output preserves all five manual-only/no-fetch/no-upload/no-scraping/live-disabled flags
- Real local outputs were inspected under `results_ledger/ledger.json`,
  `results_ledger/entries/`, and `results_ledger/reports/RESULTS_SUMMARY.md`
- Real entry captured quality score 97, compliance `ready_for_manual_upload`,
  and script/caption/thumbnail template IDs and hashes
- Mission Control localhost smoke updated the real entry to 250 views / 25 likes
  and refreshed the summary without any forbidden Fetch/Sync/Publish/OAuth button
- Mission Control showed results controls only for compliant jobs and no
  Fetch/Sync/Publish/OAuth path
- No platform API, OAuth, browser automation, upload, cloud, scraping,
  external database, paid dependency, or Phase 4E work was added

## Phase 4E — Local Performance Review Dashboard

Status: complete

Commit:
`Add Phase 4E local performance review`

Implemented:
- `performance_review.py` local CLI for deterministic review generation
- `content_factory.performance` loader, metrics, ranker, report, and atomic
  local store stack
- Missing/empty-ledger handling that still writes all five required reports
- Totals and zero-safe view-based like/comment/share/save/lead rates
- Deterministic leads/views/likes/oldest-first job ranking
- Platform, template-provenance, quality-score, and notes/lessons signals
- One deterministic next manual experiment labeled as a local, non-statistical signal
- Markdown, JSON, platform CSV, template CSV, and complete job CSV output
- Mission Control `/performance` status, totals, tables, recommendation,
  regeneration control, results-summary link, and allowlisted Markdown serving
- `performance_reports/` ignored by Git

Evidence:
- Baseline `pytest -q`: 195 passed in 92.50s
- Focused Phase 4E tests: 10 passed
- Final `pytest -q`: 205 passed in 87.27s
- `python performance_review.py --help`: passed
- Exact first-win command generated all five required files from the real ledger
- Real review captured one entry, YouTube Shorts/platform/template signals,
  quality score 97, and the manual note context
- Missing-ledger fixture produced the required empty-state wording
- Zero views returned zero rates without division errors
- Ranking and recommendations were deterministic under explicit tie tests
- JSON and Markdown retained all five required performance safety flags
- Mission Control localhost smoke returned 200/303/200 and served the report
  without forbidden fetch/sync/publish/OAuth controls
- No platform API, OAuth, metric auto-fetching, scraping, browser automation,
  auto-upload, cloud upload, external database, paid dependency, or Phase 4F
  work was added

## Phase 4F — LIT-GhostTown AI Verdict Engine Integration

Status: complete

Commits:
- LIT-GhostTown: `dcc364c Add AI verdict engine contract`
- Shorts Factory: `Add Phase 4F rich LIT verdict integration`

Implemented:
- LIT `VerdictProvider` interface and deterministic no-key mock provider
- Strict rich-verdict TypeScript schema and fail-closed validator/engine
- Backward-compatible `/api/verdict` response with ten rich evaluation fields,
  warnings, legacy source, and validated provenance
- Validator refusal for missing/extra fields, invalid scores/enums, generic
  advice, fake certainty, unsupported market claims, and malformed provenance
- Shorts Factory normalization and local validation of complete rich responses
- Explicit legacy downgrade for missing/invalid rich fields without inventing data
- Unchanged deterministic fallback when required legacy fields are invalid
- `verdict_provenance` and `verdict_warnings` in job receipts
- Inert text-only rich template placeholders and deterministic script context
- Shared `docs/contracts/LIT_VERDICT_CONTRACT.md`
- README and knowledge-base documentation

Evidence:
- LIT baseline: 20 tests; final: 25 tests, TypeScript, build, Worker dry-run
- Shorts baseline: 205 tests; final: 209 passed in 91.87s
- Focused LIT tests: 12 passed
- Focused Shorts tests: 33 passed
- Local Worker response included killer question, MVP test, work/fail reasons,
  rich risk/signals, and `provenance.validated: true`
- Real API job `e5ba29ca311e` recorded `ai_verdict_engine`, provider `mock`,
  model `mock-lit-verdict-v1`, `rich_verdict: true`, and no warnings
- Real mock job `4a626d1b9060` preserved offline deterministic behavior
- Contract tests require no network, paid AI key, or live provider
- No unrelated UI, publishing, platform API, OAuth, auto-comment, auto-DM,
  scraping, metric fetch, cloud upload, external database, or Phase 4G work

## Phase 5A — Full Autopilot Dry-Run Pipeline

Status: complete

Commit:
`Add Phase 5A full autopilot dry-run pipeline`

Implemented:
- JSON-serializable trend, idea, verdict decision, gate, publish, analytics,
  and learning-loop contracts
- Deterministic mock and local-file trend providers
- Deterministic trend-to-business-idea generation and batched existing LIT
  verdict evaluation with weak/generic/unsupported verdict rejection
- Existing Shorts Factory generation behind a batch runner
- Existing deterministic quality scorer plus autopilot-safe compliance gates
- Simulated publisher and analytics providers plus an explicit refusing live
  publisher adapter
- Durable atomic artifacts for every machine stage and receipt-based resume
- Simulated-results performance review and deterministic next-batch plan
- `autopilot.py` run/list/status/show/resume/next-plan CLI

Evidence:
- Focused Phase 5A suite: 18 passed
- Final `pytest -q`: 227 passed in 97.85s
- Existing mock orchestrator command: passed
- Exact three-job dry-run command: completed
- Real run: 3 trends, 3 ideas, 3 accepted ideas, and 3 generated shorts
- Real run: all 3 quality gates and all 3 compliance gates passed
- Real run: 9 simulated publish successes and 9 simulated analytics snapshots
- List, status, show, resume, and next-plan commands passed on the real batch
- Final receipt recorded no live publishing/attempt, platform API call,
  scraping, browser posting, credential use, or live analytics
- Runtime artifacts remained ignored under `output/`

Notes:
Phase 5A ends at the local simulated machine path. `supervised_autopilot` and
`full_autopilot` are refusing placeholders. No Phase 5B connector was started.

## Phase 5B — YouTube Official Publisher Adapter Boundary

Status: complete

Commit:
`Add Phase 5B YouTube publisher adapter boundary`

Implemented:
- `YouTubePublisherAdapter` as a structural `PublisherAdapter` implementation
- Lazy OAuth access-token, upload-scope, and expiry preflight
- Global/platform live switches, emergency stop, local quota budget, and
  explicit policy acknowledgement gates
- Top-level plan plus YouTube metadata live opt-in and approval checks
- Existing publisher metadata conversion to a validated `videos.insert`
  `snippet,status` body
- Explicit made-for-kids, privacy, media containment, title, description, tag,
  category, notification, and job-identity validation
- Future ISO-8601 scheduled publishing with mandatory private visibility
- Optional official Google API client transport and injected test transport
- Atomic redacted blocked/failed/success per-attempt receipts

Evidence:
- Phase 5A baseline focused suite: 18 passed
- Phase 5B plus Phase 5A focused suite: 25 passed
- Final `pytest -q`: 234 passed in 96.74s
- Python compile check passed
- Real one-job Phase 5A dry run completed with 3 simulated attempts
- Dry-run receipt retained `dry_run: true`, live disabled, and no credential use
- No YouTube publisher receipt directory was created by dry-run
- Missing OAuth, quota, policy, emergency-stop, approval, and invalid metadata
  cases blocked before the injected transport
- Successful adapter-path test wrote a durable receipt through a fake transport
  without a network request or real upload

Notes:
No real YouTube credentials or upload were used. TikTok, Instagram, OAuth login
UX, refresh-token storage, analytics, and Phase 5C were not started.

## Phase 5B.1 — YouTube Credential Bootstrap + Preflight

Status: complete

Commit:
`Add Phase 5B.1 YouTube credential preflight`

Implemented:
- Optional Google dependency manifest for API, auth, OAuth, and HTTP support
- `youtube_credentials.py` bootstrap/preflight/paths/dependencies CLI
- Installed-app browser OAuth requesting YouTube upload plus readonly scopes and offline access
- Atomic token storage under ignored `.local/youtube/`
- Client-secret, token, authorized-user type, both scopes, validity/refresh, and
  Git-ignore checks
- Explicit service-account and web-client refusal
- Authenticated `channels.list(mine=true)` identity check
- Redacted durable credential/quota/policy readiness receipt
- Explicit quota-console and policy-readiness confirmations
- Environment-driven adapter policy requiring the passed confirmed receipt
- Full and supervised autopilot gates unchanged and closed

Evidence:
- Baseline Phase 5A focused suite: 18 passed
- Phase 5B.1 combined focused suite: 38 passed
- Final `pytest -q`: 247 passed in 102.53s
- Python compile check passed
- CLI help, paths, and dependency status commands passed
- Default preflight refused missing OAuth library/client/token and wrote a
  durable blocked receipt with no secret data
- Git confirmed `.local/youtube/client_secret.json`, token JSON, `.env`, and
  `.env.local` are ignored
- Real one-job Phase 5A dry run completed with 3 simulated attempts, live
  disabled, credentials unused, and 0 credential artifacts
- No upload request or `videos.insert` call occurred

Notes:
The local machine still needs `google-auth-oauthlib` plus a real Desktop-app
client before bootstrap. No real consent, channel call, or upload was performed.
First supervised upload approval, TikTok, Instagram, and Phase 5C were not started.

## Phase 5B.1 Corrective — YouTube Channel Identity Scope

Status: complete

Commit:
`Fix YouTube preflight channel identity scope`

Implemented:
- `YOUTUBE_READONLY_SCOPE` and ordered `YOUTUBE_REQUIRED_SCOPES`
- Installed-app bootstrap request for upload plus readonly scopes
- Separate upload and readonly checks in token summaries and receipts
- Channel identity lookup only when the valid token contains both scopes
- Environment readiness refusal for legacy upload-only receipts
- Official transport credential construction with both required scopes
- Safe `HttpError` detail limited to HTTP status and API reason
- Explicit old-token deletion and re-bootstrap documentation

Evidence:
- Credential/publisher focused suite: 22 passed
- Phase 5A/CLI regression suite: 18 passed
- Final `pytest -q`: 249 passed in 114.91s
- Python compile check passed
- Upload-only token test failed `youtube_readonly_scope` and made zero channel calls
- Two-scope token test passed both gates and used only the fake channel backend
- HTTP error receipt test retained `status=403 reason=insufficientPermissions`
  without token, client-secret, auth-code, headers, or URL detail
- Existing dry-run credential-file guard and service-account refusal passed
- No real OAuth, channel API, or upload network call occurred

Notes:
Existing upload-only `.local/youtube/token.json` must be deleted and recreated.
Supervised/full autopilot remain disabled; no upload capability was enabled.

## Phase 5B.5 — Online-Capable Creative Angle Pack + Long-Form Assembly

Status: complete

Commit:
`Add Phase 5B.5 creative angle packs with optional LLM provider`

Implemented:
- `CreativeGenerationProvider` with deterministic, fixture, and explicit
  `online_llm` modes
- Versioned creative angle, short job, long-form plan, and receipt contracts
- Exactly five rubric-bound angles and five traceable short content packages
- YouTube-only metadata drafts with canonical GhostTownTest.com CTA
- One ordered long-form assembly plan and local Markdown script
- Per-short and long-form analytics mapping placeholders
- Content, claim, CTA, metadata, secret, traceability, and publishing gates
- Fail-closed blocked receipts without creative artifacts for invalid output
- Ignored local online-provider configuration and redacted online provenance
- Checked-in offline verdict/generated-output regression fixture

Evidence:
- Creative focused suite: 11 passed
- YouTube credential/publisher/upload/metadata/analytics regressions: 68 passed
- Phase 5A and autopilot CLI regressions: 18 passed
- Final `pytest -q`: 306 passed in 110.38s
- Python compile check and Ruff check passed
- Deterministic fixture smoke created exactly 5 angles, 5 short jobs, and 1
  long-form plan with 5 chapters
- Smoke receipt recorded 0 credentials, 0 network calls, 0 secrets, and 0
  publish attempts

Notes:
Deterministic generation remains the default and core offline path. Online LLM
generation is optional, explicit, and was not called during tests or smoke
validation. Creative analytics mappings remain pending placeholders; no
automatic learning feeds into the next batch. Phase 5A dry-run is unchanged,
and both supervised and full autopilot remain refused.

## Phase 5B.5A — Plug-and-Play LLM Model Registry

Status: complete

Commit:
`Add Phase 5B.5A plug-and-play LLM model registry`

Implemented:
- `LLMModelProfile` contracts and an override-capable `LLMModelRegistry`
- Safe checked-in fake, fixture, disabled generic HTTP, and no-schema profiles
- Ignored `.local/llm/models.json` profile overrides with credential-field refusal
- `LLMProviderAdapter` boundary with fake, local-fixture, and generic HTTP adapters
- Offline-by-default `llm_models.py` list/show/validate/test commands
- Registry-selected online creative generation with task-specific JSON schemas
- Fail-closed missing, disabled, schema-incapable, malformed, and invalid outputs
- Receipt provenance for provider/model/profile hash/adapter/tokens/cost/network
- Publishing/YouTube-action refusal and raw-response/secret non-persistence

Evidence:
- Registry + creative focused suite: 23 passed
- Creative acceptance suite: 15 passed
- Phase 5A and autopilot CLI regressions: 18 passed
- YouTube credential/publisher/upload/metadata/analytics regressions: 68 passed
- Final `pytest -q`: 318 passed in 121.61s
- Python compile check and scoped Ruff check passed
- Registry list/show/validate/fake dry-run commands passed without network
- Deterministic and `fake-json-model` online smokes each created five shorts and
  one five-chapter long-form plan
- Fake-online receipt recorded model profile hash, adapter, token/cost estimates,
  0 network calls, 0 raw responses, 0 secrets, and 0 publishing

Notes:
The generic HTTP adapter remains a credential-gated placeholder; no real LLM
provider was called. API keys remain environment-only and model profile files
reject credential fields. Deterministic mode is unchanged, creative candidates
cannot publish, and `full_autopilot` remains closed.

## Phase 5B.5B — Real Online LLM Provider Configuration + First Generation Workflow

Status: implementation complete; first credentialed provider call pending local credentials

Commit:
`Add Phase 5B.5B real online LLM generation`

Implemented:
- Safe ignored `.local/llm/models.json` initializer with `--force` overwrite gate
- Environment-variable-name-only real provider profile (`LLM_API_KEY`, `LLM_BASE_URL`)
- Generic `chat_json`/HTTP adapter with strict structured bundle schema validation
- One minimal request for five angles, five shorts, and one long-form plan
- Passed/blocked/failed attempt receipt contract with redacted errors
- Explicit no-publish, no-YouTube, no-`videos.insert`, no-secret, and no-raw-response flags
- Output gates for required angles, traceability, completeness, claims, CTA,
  secrets/auth URLs, publishing requests, and YouTube API instructions
- Offline deterministic-vs-online comparison report and CLI

Evidence:
- Registry + creative focused suite: 29 passed
- Phase 5A and autopilot CLI regressions: 18 passed
- YouTube credential/publisher/upload/metadata/analytics regressions: 68 passed
- Final `pytest -q`: 324 passed in 122.50s
- Python compile check and scoped Ruff check passed
- Local config initialized under Git-ignored `.local/llm/models.json` with no credentials
- Registry list/validate and fake-model dry-run passed offline
- Deterministic and fake-online generation each created five short jobs and one
  five-chapter long-form plan
- Comparison receipt covered five angles and passed uniqueness, completeness,
  and source quality checks
- Fake-online receipt recorded schema valid, 0 network, 0 YouTube, 0
  `videos.insert`, 0 publishing, 0 secrets, and 0 raw response storage

Notes:
No real LLM request was made because `LLM_API_KEY` and `LLM_BASE_URL` were not
present. The local profile is ready for the operator to configure and invoke
explicitly. A real call must not be followed by publishing. Online outputs are
not connected to the learning loop, and both autopilot live modes remain closed.
