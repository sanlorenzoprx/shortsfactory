# Project State

## Current status

Phase 4D is complete locally: ready-for-manual-upload jobs can now record
manual post-upload results into a local ledger, update local notes and metrics,
and roll them into a markdown summary without adding any platform integration,
metric fetching, or live publishing capability.

## Last known remote HEAD

```txt
15235dd Add Phase 4C final compliance checklist
```

## Last known commit log

```txt
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
195 passed in 96.74s
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
- Receipt JSON tracking
- Green-gate autonomous phase process

## Known constraints

- Work inside Shorts Factory unless explicitly approved.
- Do not edit LIT-GhostTown unless the user explicitly asks.
- No live publishing yet.
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

## Current risk

Phase 4D ends at local manual-results tracking. Do not begin Phase 4E or add
automatic analytics sync, deployment packaging, upload clients, remote
services, or live publisher integrations without explicit approval.
