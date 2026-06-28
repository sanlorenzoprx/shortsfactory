# Project State

## Current status

Phase 3F is complete locally: Mission Control and the CLI can view, validate,
preview, version, restore, and safely render deterministic text-only templates.
Template editing has no approval, export, upload, or publishing capability.

## Last known remote HEAD

```txt
9b938e5 Add Phase 3E manual upload kits
```

## Last known commit log

```txt
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
146 passed in 58.84s
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

## Current risk

Template changes can alter generated creative copy, so their recorded hash must
remain visible during review. Do not begin Phase 3G or add browser login
automation, remote marketplaces, upload clients, or live publisher integrations
without explicit approval.
