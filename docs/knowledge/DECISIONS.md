# Decisions

## D001 — Boring MVP before creative expansion

Status: accepted

Decision:
The first working pipeline must generate local artifacts before adding platform integrations, real publishing, or more agents.

Reason:
A boring working system beats a broad conceptual system.

## D002 — Phase order

Status: accepted

Decision:
Phase 2 order is:

1. 2A LIT API connection
2. 2B controlled Playwright app recording
3. 2C real voiceover/TTS
4. 2D background music and audio mix
5. 2E real localization
6. 2F queue and scheduler
7. 2G publisher dry-run packages

Reason:
Each phase adds one layer of reality without breaking the previous layer.

## D003 — Controlled recordings only

Status: accepted

Decision:
Phase 2B records controlled synthetic Playwright demo flows only.

Reason:
Real-user recording creates privacy and consent risk and is not needed for product footage.

## D004 — Paid/private trust posture

Status: accepted

Decision:
Paid/private workspaces should be private by default. User content, sessions, ideas, reports, and generated outputs should not be used for public examples without explicit approval.

Reason:
Trust is a product advantage.

## D005 — Green-gate autonomous development

Status: accepted

Decision:
Autonomous work may continue only one phase at a time. A phase must be tested, artifact-inspected, receipt-verified, documented, and committed before the next phase begins.

Reason:
Prevents drift, hidden failures, and uncontrolled feature expansion.

## D006 — Live publishing remains disabled

Status: accepted

Decision:
Phase 2G creates dry-run publisher packages only. It must refuse live publishing.

Reason:
Publishing needs human approval, account setup, compliance review, and platform-specific policy handling.

## D007 — No scraping in Phase 2

Status: accepted

Decision:
No Google Trends, Reddit scraping, social scraping, or platform scraping belongs in Phase 2.

Reason:
The pipeline must prove controlled production first before adding external acquisition/signal systems.

## D008 — Knowledge base must be updated before future feature work

Status: accepted

Decision:
Before Phase 3 or any new autonomous development, update and commit `docs/knowledge`.

Reason:
The repo needs durable memory so agents do not rely only on chat history.

## D009 — Local Mission Control before live publishing

Status: accepted

Decision:
Before adding live publisher integrations, Shorts Factory must have a local
Mission Control review dashboard.

Reason:
Human approval and artifact inspection are required before anything leaves the
local machine.

## D010 — Approval-gated exports before live publishing

Status: accepted

Decision:
Shorts Factory must create local approval-gated export bundles before adding
any live publisher integrations.

Reason:
A human must approve the generated content and inspect the export bundle before
anything can be uploaded manually or published later.

## D011 — Revisions require reapproval

Status: accepted

Decision:
Any revised job must be treated as a new review object and must require
approval before export.

Reason:
A revision can change the actual published message, so the original approval
cannot safely carry over.

## D012 — Quality score is advisory, not approval

Status: accepted

Decision:
Quality scoring helps humans review jobs, but it must not approve, export, or
publish content automatically.

Reason:
A deterministic score can catch missing artifacts and weak structure, but
human judgment remains the approval gate.

## D013 — Manual upload kits before live publisher APIs

Status: accepted

Decision:
Shorts Factory must generate platform-specific manual upload kits before adding
any live publisher APIs.

Reason:
Manual kits let the user verify platform-specific metadata and upload
intentionally before any automation can publish externally.

## D014 — Templates are local text assets, not executable prompts

Status: accepted

Decision:
Shorts Factory templates are editable local text assets with strict placeholder
validation. They must not execute code, call APIs, or bypass approval/export
gates.

Reason:
Creative control should not weaken local safety, reproducibility, or publishing
boundaries.

## D015 — Audit proof before Phase 4

Status: accepted

Decision:
Before adding Phase 4 or live publishing capabilities, Shorts Factory must
maintain a local audit report and demo dataset proving the end-to-end Phase 3
operating system.

Reason:
The project is now complex enough that future work needs a reproducible proof
baseline.
