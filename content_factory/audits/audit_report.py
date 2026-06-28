from __future__ import annotations

from typing import Any


FLOW = "Generate -> Score -> Review -> Revise -> Re-score -> Approve -> Export -> Manual Upload Kit -> Template Control"


def render_audit_report(receipt: dict[str, Any], evidence: dict[str, Any]) -> str:
    jobs = receipt["jobs"]
    return f"""# Phase 3 Local OS Audit

## Status

{receipt['status'].title()}

## Commit Audited

`{receipt['repo_commit']}`

## What Phase 3 Proves

{FLOW}

## Commands Run

- `pytest -q`
- `python orchestrator.py --batch 1 --locale en-US --mode mock`
- `python score_job.py --job-id <job_id> --output-root output`
- `python revise_job.py --job-id <job_id> --output-root output`
- `python export_bundle.py --job-id <job_id> --output-root output --export-root exports`
- `python upload_kit.py --job-id <job_id> --export-root exports --platform all`
- `python template_editor.py --validate script.default`
- `python template_editor.py --preview script.default`

## End-to-End Flow Evidence

### 1. Generate

Evidence: original job `{jobs['original_job_id']}`, receipt `{evidence['original_receipt']}`, media manifest `{evidence['original_media_manifest']}`.

### 2. Score

Evidence: `{evidence['original_quality']}` scored {evidence['original_score']} ({evidence['original_status']}).

### 3. Review

Evidence: Mission Control local route `/jobs/{jobs['original_job_id']}` rendered the human review and approval controls.

### 4. Revise

Evidence: revision task `{evidence['revision_task']}`, revised job `{jobs['revised_job_id']}`, and `{evidence['revision_manifest']}`.

### 5. Re-score

Evidence: `{evidence['revised_quality']}` scored {evidence['revised_score']} ({evidence['revised_status']}).

### 6. Approve

Evidence: `{evidence['approval']}` records explicit local approval after the revised job was confirmed pending.

### 7. Export

Evidence: `{evidence['export_manifest']}` records `publishing_status: not_published`, `live_publishing_enabled: false`, and detected `final.mp4`.

### 8. Manual Upload Kit

Evidence: `{evidence['upload_kit_manifest']}` plus three platform metadata/checklist directories record `manual_upload_only: true` and `api_upload_attempted: false`.

### 9. Template Control

Evidence: `{evidence['template_validation']}`, preview `{evidence['template_preview']}`, and deterministic template hash `{evidence['template_hash']}`.

## Safety Verification

- No live publishing
- No OAuth
- No platform API
- No scraping
- No real-user recording
- No external database
- No cloud worker
- Manual upload only

## Known Limits

- Local-only system
- Manual upload only
- Deterministic quality scoring
- Deterministic revision rules
- Local template editing only
- Generated media may be large and is ignored by Git

## Result

The Phase 3 local operating system is ready for controlled manual use.
"""
