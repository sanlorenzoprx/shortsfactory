# Project State

## Current status

Phase 5B.3 adds a versioned, schema-validated YouTube metadata composer so a
generated job can become supervised-upload ready without manual JSON editing.
It preserves publisher-plan binding, writes UTF-8 without BOM, defaults first
tests to private/not-for-kids, normalizes canonical tags, validates optional
website/CTA content, and emits hash receipts. The first manual supervised upload
succeeded on `Ghost Town Test` as `rnPTrNn2bgc`. Phase 5A `dry_run` remains
unchanged; `supervised_autopilot` and `full_autopilot` remain refused.

## Last known remote HEAD

```txt
3e1db5a Add Phase 5B.2 supervised YouTube upload gate
e148fae Fix YouTube preflight channel identity scope
```

## Last known commit log

```txt
e148fae Fix YouTube preflight channel identity scope
2caf12f Add Phase 5B.1 YouTube credential preflight
5855322 Add Phase 5B YouTube publisher adapter boundary
bd9b55d Add Phase 5A full autopilot dry-run pipeline
4b47c4f Add Phase 4F rich LIT verdict integration
6f33f4e Fix Mission Control revision redirect timeout
c75a58f Add Phase 4E local performance review
34cfb6e Add Phase 4D manual results ledger
15235dd Add Phase 4C final compliance checklist
d648e4b Add Phase 4B publisher preview cards
c545567 Add Phase 4A local desktop launcher
ca13c8e Add Phase 3G audit report and demo dataset
49b012d Fix Mission Control revision route
8c5bec4 Add Phase 3F local template editor
9b938e5 Add Phase 3E manual upload kits
9392193 Add Phase 3D quality scoring dashboard
47cd02b Add Phase 3C human revision queue
5187209 Add Phase 3B approval-gated export bundles
866bdf6 Add Phase 3A local mission control dashboard
d9ac9d7 Clean generated files and ignore runtime artifacts
f478817 Organize project docs and knowledge base
48fb757 Add Phase 2G dry-run publisher packages
a3edbba Add Phase 2F local queue and scheduler
53a2b4f Add Phase 2E localization support
b2a1759 Add Phase 2D background music mixing
bd8d3e3 Add Phase 2C voiceover generation
2ad9b80 Implement Phase 2A LIT API integration
```

## Last known validation

```txt
pytest -q
Phase 5A focused suite: 18 passed
Phase 5A real dry-run: 3 jobs, 9 simulated publishes, 9 simulated snapshots
Final `pytest -q`: 227 passed in 97.85s
Phase 5B focused suite: 25 passed
Phase 5B final `pytest -q`: 234 passed in 96.74s
Phase 5B dry-run smoke: 1 job, 3 simulated attempts, 0 credential reads
Phase 5B.1 focused suite: 38 passed
Phase 5B.1 final `pytest -q`: 247 passed in 102.53s
Phase 5B.1 dry-run smoke: 1 job, 3 simulated attempts, 0 credential artifacts
YouTube scope corrective focused suites: 22 passed and 18 passed
YouTube scope corrective final `pytest -q`: 249 passed in 114.91s
Phase 5B.2 focused suites: 41 passed and 18 passed
Phase 5B.2 final `pytest -q`: 268 passed in 100.23s
Phase 5B.2 dry-run smoke: 1 job, 3 simulated attempts, 0 API calls,
0 credential use, and 0 supervised upload receipts
Phase 5B.3 focused suites: 56 passed and 18 passed
Phase 5B.3 final `pytest -q`: 283 passed in 102.36s
Phase 5B.3 dry-run smoke: 1 job, 3 simulated attempts, 0 API calls,
0 credential use, V1 metadata, UTF-8 without BOM, and 0 upload receipts
```

## Known working capabilities

- Local mock short generation
- Real LIT API integration with safe fallback
- Controlled Playwright app recording
- Real SAPI voiceover generation
- Background music mixing
- Deterministic en-US / es-PR localization
- Local queue and scheduler
- Dry-run publisher packages
- Local Mission Control job and artifact review
- Local pending / approved / rejected / needs-revision decisions
- Approval-gated local export bundles with deterministic replacement
- Export manifests that explicitly disable live publishing
- Human revision tasks with queued, complete, and failed local states
- Deterministic revised jobs with immutable source lineage
- Mandatory separate approval for every revised job
- Mission Control revision runs redirect directly to the new pending revised job
- Deterministic nine-category local quality scoring
- Mission Control score/status, issues, fixes, and readiness dashboard
- Advisory quality gates that cannot approve or export automatically
- Platform-specific local manual upload kits for three supported platforms
- Deterministic titles, captions, descriptions, hashtag caps, and checklists
- Mission Control upload-kit status and safely escaped previews
- Local built-in and editable template registry
- Strict placeholder/schema/path validation with deterministic hashes
- Atomic local template saves, ignored history, and validated restore
- Mission Control template editing, validation, history, restore, and preview
- Script, upload-kit, and revision template use with deterministic fallbacks
- Job receipt template ID/hash provenance
- One-command Phase 3 local OS audit and demo evidence package
- Default media manifests without copying large generated media
- Audit receipt with all nine flow steps and mandatory publishing safety flags
- Space-safe local launcher menu and non-interactive operator shortcuts
- Local health report for dependencies, roots, templates, Git safety, and CLIs
- Localhost-only Mission Control launch command
- Static local YouTube Shorts, TikTok, and Instagram Reels preview cards
- Preview provenance/safety refusal and offline advisory platform checks
- Mission Control preview generation, links, and allowlisted static serving
- Final compliance checklist JSON/Markdown under ignored upload-kit folders
- Deterministic prerequisite, safety, placeholder, and risky-wording checks
- Explicit local human confirmation gate before manual upload readiness
- Mission Control compliance generation, open links, readiness status, and
  mark-reviewed action
- Local manual results ledger entries, ledger index, and markdown summary
- Deterministic ready-for-manual-upload prerequisite checks before results entry
- Manual URL, metric, note, template, quality, and compliance context capture
- Mission Control local results record/update section and summary link
- Deterministic manual-results performance totals and zero-safe rates
- Leads/views/likes/oldest-first job ranking and platform/template summaries
- Captured quality-score signals plus local notes and lessons review
- Deterministic next-manual-experiment recommendation without an LLM
- Local Markdown, JSON, and three CSV performance reports
- Mission Control performance status, tables, recommendation, regeneration,
  and allowlisted Markdown report view
- Cross-repo LIT rich-verdict contract with legacy fields preserved
- Deterministic no-key mock verdict provider behind a provider interface
- Strict LIT rich schema validation for fields, enums, specificity, certainty,
  unsupported claims, warnings, and provenance
- Rich Ghost Town, buyer, distribution, business-model, killer-question, and
  MVP-test fields available to Shorts Factory templates as inert text
- Receipt-level `verdict_provenance` and `verdict_warnings`
- Legacy-rich downgrade warnings and unchanged invalid-legacy `api_fallback`
- Receipt-driven Phase 5A dry-run autopilot with stage-level resume
- Deterministic mock and local-file trend provider boundaries
- Programmatic trend-to-business-idea generation and LIT verdict batch filter
- Existing short generator plus deterministic quality/compliance machine gates
- Simulated publisher and analytics adapters with refusing live adapter
- Local performance review and deterministic next-batch experiment receipt
- Batch list/status/show/resume/next-plan CLI inspection
- YouTube official publisher adapter and injectable upload transport boundary
- Lazy OAuth credential preflight with upload-scope and expiry checks
- Two-key live enablement, local quota budget, and policy acknowledgement gates
- Existing publisher metadata to validated `videos.insert` payload conversion
- Future private scheduled-publish payload support
- Redacted durable per-attempt YouTube publish receipts
- Optional Google dependency manifest and lazy installed-app OAuth imports
- Local browser OAuth bootstrap requesting upload plus readonly scopes
- Git-ignored client-secret and authorized-user token paths
- Refreshable/valid token with explicit upload and readonly scope preflight
- Authenticated channel title/id verification with no upload call
- Durable redacted credential, quota, and policy readiness receipt
- Environment live policy requiring a passed, explicitly confirmed receipt
- Safe channel `HttpError` status/reason receipt detail without request secrets
- Separate one-video supervised YouTube upload CLI and orchestrator
- Generated-artifact trust chain through content, batch, LIT, quality, and compliance receipts
- Exact Ghost Town Test channel confirmation and three per-invocation approvals
- Immutable blocked/attempted/success/failure supervised upload receipts
- Versioned `youtube_upload_metadata.v1` contract and legacy upgrade validation
- One-job metadata hardening CLI with publisher-plan and generation-receipt binding
- Canonical tag normalization plus validated website/CTA composition
- UTF-8 no-BOM metadata output and immutable before/after hash receipts
- Receipt JSON tracking
- Green-gate autonomous phase process

## Known constraints

- Work inside Shorts Factory unless explicitly approved.
- Do not edit LIT-GhostTown unless the user explicitly asks.
- No unsupervised or automatic live publishing.
- No real-user recording.
- No scraping.
- No cloud workers.
- No paid API dependency for core tests.
- Dry-run publisher packages require human approval before any real publishing.
- Mission Control approval records are local JSON files under `output/approvals/`.
- Export bundles are local generated artifacts under `exports/approved/` and
  are ignored by Git.
- Revision tasks and revised job outputs remain local under `output/` and are
  ignored by Git.
- Quality reports remain local under `output/quality/` and are ignored by Git.
- Manual upload kits remain local under `exports/upload_kits/` and are ignored
  by Git.
- Editable template copies remain local under `templates/`; generated
  `templates/history/` and `templates/local/` are ignored by Git.
- Templates are text only and cannot execute expressions, code, shell commands,
  imports, HTML, network requests, approval, export, or publishing actions.
- Generated `demo_dataset/` evidence is local and ignored by Git; only the
  lightweight Markdown audit report is committed.
- The launcher runs child scripts with list arguments, `shell=False`, absolute
  paths, and no timers or hidden background scheduling.
- Preview cards live under ignored `exports/upload_kits/`; HTML is escaped and
  contains no remote scripts, styles, tracking, account, upload, or post action.
- Compliance checklists live under ignored `exports/upload_kits/<job_id>/compliance/`;
  they remain local Markdown/JSON only and cannot publish or upload.
- Manual results live under ignored `results_ledger/`; entries and summaries are
  local operator records only and cannot fetch metrics, upload, or publish.
- Performance reviews live under ignored `performance_reports/`; they are local
  derived reports only and cannot fetch URLs or metrics, scrape, upload, or publish.
- Phase 4F provider output is evaluated and validated in LIT-GhostTown. Shorts
  Factory never invents missing business conclusions and only formats validated
  rich or backward-compatible legacy fields.
- Phase 5A runtime state lives under ignored `output/autopilot/batches/`.
- The Phase 5A runner still refuses `supervised_autopilot` and
  `full_autopilot`; Phase 5B.2 is a separate one-shot CLI and is never selected
  by the batch runner.
- Real YouTube setup still requires an approved Google Cloud project, enabled
  YouTube Data API, OAuth consent/client configuration, token lifecycle,
  available upload quota, policy review, and optional Google client packages.
- Local YouTube secrets default to `.local/youtube/client_secret.json` and
  `.local/youtube/token.json`; `.local/youtube/` is ignored by Git.
- The credential preflight receipt cannot enable either supervised or full
  autopilot. It is only one required input to the explicit Phase 5B.2 command.
- Supervised upload receipts live under ignored
  `output/youtube/supervised_uploads/<attempt_id>/` and are never overwritten.
- Metadata hardening must operate on the YouTube metadata referenced by the
  generated publisher plan; manual sidecars remain untrusted unless the plan is
  intentionally updated.
- Metadata hardening receipts live under ignored
  `output/youtube/metadata_hardening/<job_id>/`.

## Current risk

The authenticated credential preflight identifies `Ghost Town Test` as channel
`UCIzMYpBt3WdSXZBrvoE7eCg`. The first manual upload succeeded at
`https://www.youtube.com/watch?v=rnPTrNn2bgc`; tests still use only injected fake
transports. Future uploads must harden one generated job, review the emitted
metadata and receipt, review quota/policy, and manually invoke the supervised
command. YouTube analytics, TikTok, Instagram, remote trend connectors, and
automatic live publishing remain out of scope.
