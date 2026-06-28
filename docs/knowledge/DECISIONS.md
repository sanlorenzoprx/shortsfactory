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
