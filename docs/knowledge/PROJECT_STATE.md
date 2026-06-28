# Project State

## Current status

Phase 2 is complete through Phase 2G and pushed to `origin/main`.

## Last known remote HEAD

```txt
48fb757 Add Phase 2G dry-run publisher packages
```

## Last known commit log

```txt
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
44 passed in 63.06s
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

## Current untracked files reported by user

```txt
?? PHASE_2A_RECEIPT.md
?? "SHORTS_FACTORY_KNOWLEDGE_BASE_AND_AUTONOMOUS_GOVERNANCE_HANDOFF (1).md"
?? output/jobs/d1be5b686709/
```

Recommended handling:

- Do not commit `output/jobs/d1be5b686709/` unless there is a specific reason to preserve it as a fixture.
- Fold useful content from `PHASE_2A_RECEIPT.md` into `docs/knowledge/PHASE_RECEIPTS.md`, then decide whether to delete or keep it.
- Do not commit the handoff file unless you want repo-local handoff history.

## Current risk

The project is now mature enough that further autonomous development should not proceed without updating this knowledge base first.
