# Autonomous Development Rules

## Read first

Before implementing anything, read:

- `docs/knowledge/PROJECT_STATE.md`
- `docs/knowledge/DECISIONS.md`
- `docs/knowledge/PHASE_RECEIPTS.md`
- `docs/knowledge/AUTONOMOUS_RULES.md`
- `docs/knowledge/ROADMAP.md`

## Work rule

Work one phase or one bounded task at a time.

Do not combine multiple phases into one implementation pass unless the user explicitly approves it.

## Green gate

A phase is not complete until:

- tests pass
- prescribed commands pass
- real artifacts are inspected
- `receipt.json` contains expected metadata
- README is updated
- knowledge base is updated
- changes are committed

## Stop rules

Stop immediately if:

- a required secret is missing
- the same failure repeats twice
- the fix requires editing another repo
- the task requires Codex to invoke a real live upload; implementation and
  fake-transport tests of an explicitly approved supervised gate are allowed
- the task requires real-user recording
- the task requires scraping
- the task requires cloud workers
- tests must be weakened to pass
- the agent is unsure which phase is active
- the agent cannot verify the generated artifacts

## Commit rule

Every completed phase gets its own commit.

Do not combine multiple phases in one commit.

## No silent scope expansion

Never add:

- live publishing
- real-user recording
- scraping
- paid API dependency for core tests
- cloud workers
- new product behavior outside the current phase
- platform account integration without explicit approval

## Artifact rule

Do not commit generated output folders by default.

Generated outputs such as `output/jobs/...` should remain untracked unless intentionally promoted to a small fixture.

## Publisher rule

Publisher packages are dry-run only until the user explicitly approves live publishing.

YouTube credential preflight requires both `youtube.upload` and
`youtube.readonly`; readonly is used only for authenticated channel identity.
An upload-only token must not trigger `channels.list` and cannot produce a
ready receipt. Credential preflight never calls `videos.insert`.

Phase 5B.2 permits only Hector to manually invoke
`youtube_supervised_upload.py` for one explicitly selected, receipt-bound video.
The Phase 5A runner must continue refusing `supervised_autopilot` and
`full_autopilot`. No agent, scheduler, batch runner, test, or dry-run may invoke
the real upload transport. Attempt and final receipts must be separate and
immutable.

Phase 5B.3 metadata preparation must use `youtube_metadata.py harden` against
the generated metadata referenced by the publisher plan. Do not manually patch
JSON or create an unreferenced sidecar. Metadata output must pass the versioned
contract, contain no secrets/authentication URLs, and be valid UTF-8 without a
BOM. Website and CTA text may enter upload metadata only through this validated
composer. Metadata hardening never authorizes or invokes an upload.

Phase 5B.4 verification and analytics are read-only and may run only through
their explicit local CLIs. Verification may call `videos.list`; analytics may
call YouTube Analytics `reports.query` only when the optional analytics scope
is present. Neither path may import or call `videos.insert`, and neither may be
wired into Phase 5A batch autopilot. Performance and country reports write
separate receipts; an unsupported metric/dimension combination must soft-block
only that report with a redacted reason.

Phase 5B.5 creative generation defaults to the deterministic provider. Fixture
mode may read only checked-in fixture input/output. `online_llm` requires an
explicit CLI provider flag plus ignored local/environment configuration. Before
any online call, reject secrets and authentication URLs in provider input.
Never persist an API key, raw provider response, or unsafe prompt. Every provider
output must pass the same contracts and creative gates; invalid online output
writes only a blocked redacted receipt. Creative metadata remains a draft and
must not invoke credentials, uploads, verification, analytics, supervised
autopilot, or full autopilot.
