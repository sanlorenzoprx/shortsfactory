# SHORTS FACTORY KNOWLEDGE BASE + AUTONOMOUS GOVERNANCE HANDOFF

## Objective

Before any more autonomous Phase 2 work continues, create a durable project knowledge base inside the Shorts Factory repo.

The system is now moving fast enough that the next bottleneck is not code generation. The next bottleneck is memory, accountability, and preventing autonomous work from drifting away from what has already been tried, proven, committed, or rejected.

This handoff creates a repo-native knowledge base that records:

- what has been tried
- what worked
- what failed
- what was committed
- what is still uncommitted
- what artifacts prove success
- what rules autonomous development must obey
- what phases are approved next
- what phases are blocked

## Hard stop rule

Do not continue Phase 2E, 2F, 2G, or any future implementation until this knowledge base exists and is committed.

If Phase 2E is currently mid-run, finish only the current verification command. Then stop. Do not start 2F.

## Why this matters

Autonomous development only stays safe when every loop has:

- a clear contract
- a verifier
- a budget or cap
- proof artifacts
- a memory trail
- a stop condition

Without this, the agent can continue adding features while losing the project’s actual decisions.

## Required repo structure

Create this folder structure:

```txt
docs/
  knowledge/
    README.md
    PROJECT_STATE.md
    DECISIONS.md
    EXPERIMENTS.md
    PHASE_RECEIPTS.md
    GREEN_GATE_LOG.md
    AUTONOMOUS_RULES.md
    ROADMAP.md
    OPEN_QUESTIONS.md
```

Do not replace the normal README. This is an internal development memory system.

## Required files

### 1. docs/knowledge/README.md

Purpose:

Explain how to use the knowledge base.

Must include:

- this is the source of truth for autonomous development
- every phase must update the knowledge base before commit
- agents must read it before starting work
- agents must append receipts after finishing work
- do not delete historical decisions; supersede them with a dated note

### 2. docs/knowledge/PROJECT_STATE.md

Purpose:

A one-page current snapshot.

Must include:

```md
# Project State

## Current Phase

Phase 2E if still in progress, or Phase 2F if Phase 2E has been committed.

## Last Known Good Commit

- Phase 2C: bd8d3e3 Add Phase 2C voiceover generation
- Phase 2D: b2a1759 Add Phase 2D background music mixing
- Phase 2E: pending until committed

## Known Working Capabilities

- Mock short generation
- Real LIT API integration with safe fallback
- Controlled Playwright app recording
- Real SAPI voiceover generation
- Background music mixing
- Receipt JSON tracking
- Green-gate autonomous phase process

## Known Constraints

- Work inside Shorts Factory unless explicitly approved.
- Do not edit LIT-GhostTown without stopping and asking.
- No live publishing yet.
- No real-user recording.
- No scraping.
- No cloud workers.
- No hidden dependencies on paid APIs for core tests.

## Current Risk

Autonomous development is now fast enough that project memory must be formalized before more phases continue.
```

### 3. docs/knowledge/DECISIONS.md

Purpose:

Record what the project has committed to.

Start with these decisions:

```md
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
2A LIT API connection
2B controlled Playwright app recording
2C real voiceover/TTS
2D background music and audio mix
2E real localization
2F queue and scheduler
2G publisher dry-run packages

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
Paid workspaces should be private by default. User content, sessions, and ideas should not be used for public examples without explicit approval.

Reason:
Trust is a product advantage.

## D005 — Green-gate autonomous development

Status: accepted

Decision:
Autonomous work may continue only one phase at a time. A phase must be tested, artifact-inspected, receipt-verified, and committed before the next phase begins.

Reason:
Prevents drift, hidden failures, and uncontrolled feature expansion.
```

### 4. docs/knowledge/EXPERIMENTS.md

Purpose:

Record what was tried and the outcome.

Must include at least:

```md
# Experiments

## E001 — Local mock video generation

Result: worked

Evidence:
- Real script.txt
- Real captions.srt
- Real thumbnail.jpg
- Real 1080x1920 H.264 MP4
- receipt.json
- tests passed

## E002 — LIT API fallback

Result: worked

Evidence:
- API mode completes when LIT endpoint is unavailable
- receipt.json records api_fallback warning

## E003 — Real local LIT API mode

Result: worked

Evidence:
- source: lit_api
- raw lit_api_response.json saved
- output short generated

## E004 — Playwright app recording

Result: worked after selector fix

Problem:
[name="description"] matched the page meta description.

Fix:
Use stable app selectors/test IDs.

Evidence:
- app_recording_raw.webm
- app_recording.mp4
- app_recording_final.png
- recording.status: success
- 1080x1920 verified

## E005 — Real SAPI voiceover

Result: worked

Evidence:
- PCM WAV voiceover
- final MP4 includes AAC audio
- Phase 2C commit: bd8d3e3

## E006 — Background music mix

Result: worked

Evidence:
- H.264 1080x1920 final MP4 with AAC audio
- voice retention correlation: 0.997021
- Phase 2D commit: b2a1759
```

### 5. docs/knowledge/PHASE_RECEIPTS.md

Purpose:

One running receipt of each completed phase.

Must include:

```md
# Phase Receipts

## Phase 1 / MVP

Status: complete

Outputs:
- script.txt
- captions.srt
- thumbnail.jpg
- short.mp4
- receipt.json

## Phase 2A — LIT API Connection

Status: complete

Implemented:
- Real LIT HTTP client
- Configurable URL and timeout
- Optional Bearer auth
- Response normalization
- Strict verdict validation
- Safe API fallback
- raw lit_api_response.json on success
- tests and README instructions

## Phase 2B — Controlled Playwright Recording

Status: complete

Implemented:
- recorder
- CLI flag
- raw WebM
- normalized MP4
- final screenshot
- receipt metadata
- tests

## Phase 2C — Real Voiceover/TTS

Status: complete

Commit:
bd8d3e3 Add Phase 2C voiceover generation

Evidence:
- 23 tests passed
- Real SAPI voiceover
- 25.216s PCM WAV
- Final MP4 AAC audio + H.264 1080x1920

## Phase 2D — Background Music Mixing

Status: complete

Commit:
b2a1759 Add Phase 2D background music mixing

Evidence:
- 27 tests passed
- Final MP4 H.264 1080x1920 with AAC audio
- Voice retention correlation: 0.997021

## Phase 2E — Real Localization

Status:
Pending unless already committed.

Required evidence before marking complete:
- pytest passes
- en-US mock passes
- es-PR mock passes
- es-PR api + record-app + tts + music passes
- receipt contains localization metadata
- Spanish artifacts inspected
- commit hash recorded
```

### 6. docs/knowledge/GREEN_GATE_LOG.md

Purpose:

A chronological gate log.

Format:

```md
# Green Gate Log

## YYYY-MM-DD — Phase Name

Status: passed | failed | blocked | pending

Commands run:
- command
- command

Artifacts inspected:
- path
- path

Receipt fields verified:
- field
- field

Commit:
hash message

Notes:
- anything important
```

Add entries for:

- Phase 2C
- Phase 2D
- Phase 2E if complete

### 7. docs/knowledge/AUTONOMOUS_RULES.md

Purpose:

Rules every future agent run must follow.

Must include:

```md
# Autonomous Development Rules

## Read first

Before implementing anything, read:

- docs/knowledge/PROJECT_STATE.md
- docs/knowledge/DECISIONS.md
- docs/knowledge/PHASE_RECEIPTS.md
- docs/knowledge/AUTONOMOUS_RULES.md

## Work rule

Work one phase at a time.

## Green gate

A phase is not complete until:

- tests pass
- prescribed commands pass
- real artifacts are inspected
- receipt.json contains expected metadata
- README is updated
- knowledge base is updated
- changes are committed

## Stop rules

Stop immediately if:

- a required secret is missing
- the same failure repeats twice
- the fix requires editing another repo
- the task requires live publishing
- the task requires real-user recording
- the task requires scraping
- tests must be weakened to pass
- the agent is unsure which phase is active

## Commit rule

Every completed phase gets its own commit.

Do not combine multiple phases in one commit.

## No silent scope expansion

Never add:

- live publishing
- real-user recording
- scraping
- paid API dependency for tests
- cloud workers
- new product behavior outside the current phase
```

### 8. docs/knowledge/ROADMAP.md

Purpose:

Approved next steps.

Must include:

```md
# Roadmap

## Completed

- MVP local mock pipeline
- Phase 2A LIT API connection
- Phase 2B controlled Playwright recording
- Phase 2C real voiceover/TTS
- Phase 2D background music mixing

## In progress

- Phase 2E real localization

## Next

- Phase 2F queue and scheduler
- Phase 2G publisher dry-run packages

## Explicitly not yet

- live publishing
- real-user recording
- scraping
- cloud worker deployment
- platform API posting
- monetization/payment workflow
```

### 9. docs/knowledge/OPEN_QUESTIONS.md

Purpose:

Questions that should stop or guide future work.

Start with:

```md
# Open Questions

## Q001 — Which locales after es-PR?

Current answer:
Not decided. Do not add more locales without approval.

## Q002 — Which publishers first?

Current answer:
No live publisher integration yet. Phase 2G is dry-run package generation only.

## Q003 — Should real-user recording exist?

Current answer:
Not in Shorts Factory Phase 2. Future privacy/product discussion only.

## Q004 — Should LIT-GhostTown be edited again?

Current answer:
No. Stop and ask first unless a handoff explicitly allows it.
```

## Implementation sequence

1. Create the docs/knowledge folder.
2. Add all required files.
3. Fill with current known project state.
4. Run markdown/text sanity check if available.
5. Run `pytest -q` to ensure no code was accidentally changed.
6. Commit:

```bash
git add docs/knowledge
git commit -m "Add project knowledge base and autonomous rules"
```

## Acceptance criteria

This task is complete only when:

- all required knowledge files exist
- they include the current known phase history
- Phase 2C and 2D commit hashes are recorded
- autonomous stop rules are explicit
- roadmap reflects 2E in progress unless already committed
- `pytest -q` passes
- git commit is created

## Stop condition

After committing this knowledge base, stop and report.

Do not resume Phase 2E, 2F, or 2G until the user explicitly says to continue.
