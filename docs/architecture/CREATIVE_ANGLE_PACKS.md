# Creative Angle Packs

Phase 5B.5 converts one trending business idea and its stored LIT verdict into
five comparable creative experiments:

1. `ghost_town_risk`
2. `buyer_reality`
3. `fast_validation_test`
4. `contrarian_opportunity`
5. `builder_action_plan`

Each experiment receives a traceable `AngleShortJob` containing its hook,
title, script, caption, thumbnail text, canonical GhostTownTest.com CTA, tags,
hashtags, YouTube metadata draft, source receipts, and empty analytics mapping
fields. The five jobs are assembled—without rendering or publishing—into one
`LongFormAssemblyPlan` with ordered chapters, transitions, conclusion,
description, and suggested timestamps.

## Flow and ownership

```txt
stored trend idea + LIT verdict
  -> provider generates structured creative candidates
  -> contracts validate shape and traceability
  -> creative gates validate specificity, claims, CTA, metadata, and safety
  -> orchestrator writes short and long-form drafts
  -> redacted receipt is written last
```

Providers generate creative text only. The orchestrator owns IDs, source
references, output locations, analytics placeholders, and publishing safety.
Failed schema or blocking-gate results write only `ANGLE_PACK_RECEIPT.json`.

## Frontend/backend integration

A future UI can read `creative_angle_pack.json` and the five short jobs to show
why each angle was chosen, hook style, predicted viewer trigger, script,
thumbnail/keyframe text, CTA, and the long-form plan. `expected_behavior_signal`
is a hypothesis, not measured performance. Prior learning may be displayed only
after a future phase provides a receipt-backed offline mapping.

Analytics placeholders remain null with `data_quality: pending`. Phase 5B.5
does not query YouTube or feed performance into the next batch.

## Safety boundary

All YouTube metadata is `draft_not_upload_ready`. Creative generation never
loads YouTube credentials or calls an upload, verification, or analytics API.
The existing one-video supervised uploader remains the only approved publishing
boundary. Both autopilot live modes remain closed.
