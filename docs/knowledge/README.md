# Shorts Factory Knowledge Base

This folder is the repo-native memory system for Shorts Factory.

It exists because autonomous development is now moving fast enough that the project needs a durable source of truth for:

- what has been tried
- what worked
- what failed
- what was committed
- what is intentionally out of scope
- what must be verified before work continues

## Required agent behavior

Before any future implementation, the agent must read:

1. `docs/knowledge/PROJECT_STATE.md`
2. `docs/knowledge/DECISIONS.md`
3. `docs/knowledge/PHASE_RECEIPTS.md`
4. `docs/knowledge/AUTONOMOUS_RULES.md`
5. `docs/knowledge/ROADMAP.md`

After finishing any phase, the agent must update:

1. `docs/knowledge/PROJECT_STATE.md`
2. `docs/knowledge/PHASE_RECEIPTS.md`
3. `docs/knowledge/GREEN_GATE_LOG.md`
4. `docs/knowledge/EXPERIMENTS.md` if something new was learned
5. `docs/knowledge/OPEN_QUESTIONS.md` if a decision is needed

## Historical rule

Do not delete old decisions or receipts.

If a decision changes, add a new dated/superseding decision in `DECISIONS.md`.
