from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

from .job_index import JobRecord


DRY_RUN_LABEL = "DRY RUN ONLY — NOT PUBLISHED"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _url_job_id(job_id: str) -> str:
    return quote(job_id, safe="")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} · Shorts Factory</title>
  <link rel="stylesheet" href="/static/mission_control.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">SHORTS FACTORY <span>MISSION CONTROL</span></a>
    <div class="local-badge">LOCAL ONLY</div>
  </header>
  <main>{body}</main>
</body>
</html>"""


def _state_badge(state: str) -> str:
    label = state.replace("_", " ").title()
    return f'<span class="state state-{_escape(state)}">{_escape(label)}</span>'


def render_index(
    jobs: list[JobRecord],
    approvals: dict[str, dict[str, object]],
    quality_reports: dict[str, dict[str, object] | None] | None = None,
) -> str:
    quality_reports = quality_reports or {}
    rows = []
    for job in jobs:
        approval = approvals.get(job.job_id, {"state": "pending"})
        state = str(approval.get("state", "pending"))
        warning = (
            f'<span class="warning-count">{job.warning_count}</span>'
            if job.warning_count
            else '<span class="quiet">0</span>'
        )
        quality = quality_reports.get(job.job_id)
        quality_cell = (
            f'<span class="quality-badge quality-{_escape(quality.get("status", "warn"))}">{_escape(quality.get("overall_score", "—"))} · {_escape(quality.get("status", "unknown"))}</span>'
            if quality is not None
            else '<span class="quiet">Not scored</span>'
        )
        rows.append(
            f"""<tr>
  <td><a class="job-link" href="/jobs/{_url_job_id(job.job_id)}">{_escape(job.job_id)}</a></td>
  <td>{_state_badge(state)}</td>
  <td>{quality_cell}</td>
  <td>{_escape(job.status)}</td>
  <td>{_escape(job.locale)}</td>
  <td>{_escape(job.mode)}</td>
  <td>{_escape(job.created_at)}</td>
  <td>{warning}</td>
</tr>"""
        )
    if rows:
        table_body = "\n".join(rows)
    else:
        table_body = '<tr><td colspan="8" class="empty">No receipt-backed jobs found.</td></tr>'
    body = f"""
<section class="hero">
  <p class="eyebrow">Human review gate</p>
  <h1>Generated jobs</h1>
  <p>Inspect local artifacts and record approval decisions. Nothing here publishes.</p>
</section>
<section class="panel job-index">
  <div class="panel-heading"><h2>Review queue</h2><span>{len(jobs)} jobs</span></div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Job</th><th>Approval</th><th>Quality</th><th>Status</th><th>Locale</th><th>Mode</th><th>Created</th><th>Warnings</th></tr></thead>
      <tbody>{table_body}</tbody>
    </table>
  </div>
</section>"""
    return _page("Mission Control", body)


def _read_text(path: Path | None) -> str:
    if path is None:
        return "Not available"
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return f"Could not read artifact: {exc}"


def _json_text(path: Path | None, fallback: dict | None = None) -> str:
    if path is None:
        value = fallback if fallback is not None else {"status": "not available"}
        return json.dumps(value, indent=2, ensure_ascii=False)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return f"Could not read JSON artifact: {exc}"


def _artifact_url(job: JobRecord, artifact_name: str) -> str:
    return f"/artifacts/{_url_job_id(job.job_id)}/{quote(artifact_name, safe='')}"


def render_job_detail(
    job: JobRecord,
    approval: dict[str, object],
    export_manifest: dict[str, object] | None = None,
    revision_task: dict[str, object] | None = None,
    revision_manifest: dict[str, object] | None = None,
    quality_report: dict[str, object] | None = None,
    upload_kit_preview: dict[str, object] | None = None,
) -> str:
    state = str(approval.get("state", "pending"))
    video_name = next(
        (
            name
            for name in (
                "final.mp4",
                "short_with_music.mp4",
                "short_with_voice.mp4",
                "short.mp4",
                "app_recording.mp4",
            )
            if name in job.artifacts
        ),
        None,
    )
    video = (
        f'<video controls preload="metadata" src="{_artifact_url(job, video_name)}"></video>'
        if video_name
        else '<div class="missing">No generated MP4 available</div>'
    )
    thumbnail = (
        f'<img src="{_artifact_url(job, "thumbnail.jpg")}" alt="Thumbnail for job {_escape(job.job_id)}">'
        if "thumbnail.jpg" in job.artifacts
        else '<div class="missing">No thumbnail available</div>'
    )
    warnings = (
        "".join(f"<li>{_escape(warning)}</li>" for warning in job.warnings)
        if job.warnings
        else '<li class="quiet">No warnings recorded.</li>'
    )
    script = _escape(_read_text(job.artifacts.get("script.txt")))
    captions = _escape(_read_text(job.artifacts.get("captions.srt")))
    receipt = _escape(_json_text(job.artifacts.get("receipt.json"), job.receipt))
    publisher_path = job.artifacts.get("publisher_package.json")
    publisher = _escape(_json_text(publisher_path))
    publisher_class = "" if publisher_path else " muted-panel"
    notes = _escape(approval.get("notes", ""))
    updated = _escape(approval.get("updated_at") or "Not yet reviewed")
    if state != "approved":
        export_panel = """
<section class="panel export-panel">
  <div class="panel-heading"><h2>Approved export bundle</h2><span>Local only</span></div>
  <div class="export-content"><p>Approve this job before export.</p><p class="quiet">No files are uploaded or published.</p></div>
</section>"""
    elif export_manifest is None:
        export_panel = f"""
<section class="panel export-panel">
  <div class="panel-heading"><h2>Approved export bundle</h2><span>Not exported</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/export">
    <p>Build a deterministic local bundle for manual review or upload.</p>
    <button class="export" type="submit">Export Approved Bundle</button>
    <p class="quiet">This action does not publish or contact a platform.</p>
  </form>
</section>"""
    else:
        export_json = _escape(json.dumps(export_manifest, indent=2, ensure_ascii=False))
        export_dir = _escape(export_manifest.get("export_dir", "exports/approved"))
        export_panel = f"""
<section class="panel export-panel">
  <div class="panel-heading"><h2>Approved export bundle</h2><span>Exported · not published</span></div>
  <div class="export-content"><p>Local folder: <code>{export_dir}</code></p></div>
  <pre>{export_json}</pre>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/export">
    <button class="export" type="submit">Refresh Approved Bundle</button>
    <p class="quiet">Local replacement only. Live publishing remains disabled.</p>
  </form>
</section>"""
    if revision_manifest is not None:
        original_id = str(revision_manifest.get("original_job_id", "unknown"))
        revision_json = _escape(
            json.dumps(revision_manifest, indent=2, ensure_ascii=False)
        )
        revision_panel = f"""
<section class="panel revision-panel">
  <div class="panel-heading"><h2>Revision lineage</h2><span class="reapproval-badge">Requires reapproval</span></div>
  <div class="revision-content"><p>Original job: <a href="/jobs/{_url_job_id(original_id)}">{_escape(original_id)}</a></p><p>This revised job has its own approval state. Original approval does not carry over.</p></div>
  <pre>{revision_json}</pre>
</section>"""
    else:
        task_note = (
            str(revision_task.get("revision_note", ""))
            if revision_task is not None
            else str(approval.get("notes", ""))
        )
        warning = (
            '<p class="revision-warning">This job is already approved. Creating a revision will require reapproval.</p>'
            if state == "approved"
            else ""
        )
        task_details = ""
        run_action = ""
        if revision_task is not None:
            task_state = str(revision_task.get("state", "unknown"))
            task_json = _escape(json.dumps(revision_task, indent=2, ensure_ascii=False))
            task_details = f'<div class="panel-heading subheading"><h3>Revision task</h3><span>{_escape(task_state)}</span></div><pre>{task_json}</pre>'
            if task_state in {"revision_queued", "revision_failed"}:
                run_action = f"""
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/run-revision">
    <button class="revise" type="submit">Run Local Revision</button>
    <p class="quiet">Creates a new pending job. The original stays untouched.</p>
  </form>"""
            elif task_state == "revision_complete" and revision_task.get("revised_job_id"):
                revised_id = str(revision_task["revised_job_id"])
                run_action = f'<div class="revision-content"><p>Revised job: <a href="/jobs/{_url_job_id(revised_id)}">{_escape(revised_id)}</a></p></div>'
        revision_panel = f"""
<section class="panel revision-panel">
  <div class="panel-heading"><h2>Human revision</h2><span>Deterministic local rules</span></div>
  <div class="revision-content">{warning}<p>Describe the specific change. Creating a task marks this job Needs Revision.</p></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/revision-task">
    <label for="revision-note">Revision note</label>
    <textarea id="revision-note" name="revision_note" rows="4" required placeholder="Example: tighten hook and make CTA clearer">{_escape(task_note)}</textarea>
    <button class="revise" type="submit">Create Revision Task</button>
  </form>
  {task_details}
  {run_action}
</section>"""
    if quality_report is None:
        quality_panel = f"""
<section class="panel quality-panel">
  <div class="panel-heading"><h2>Quality score</h2><span>Not scored</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/score">
    <p>Run deterministic local checks before approval, revision, or export.</p>
    <button class="score" type="submit">Score Job</button>
    <p class="quiet">Scoring is advisory and never changes approval or export state.</p>
  </form>
</section>"""
    else:
        quality_status = str(quality_report.get("status", "unknown"))
        overall_score = quality_report.get("overall_score", "—")
        categories = quality_report.get("category_scores", {})
        if not isinstance(categories, dict):
            categories = {}
        category_rows = "".join(
            f"<tr><th>{_escape(name.replace('_', ' ').title())}</th><td>{_escape(score)}</td></tr>"
            for name, score in categories.items()
        )
        quality_issues = quality_report.get("issues", [])
        if not isinstance(quality_issues, list):
            quality_issues = []
        issue_rows = []
        for quality_issue in quality_issues:
            if not isinstance(quality_issue, dict):
                continue
            issue_rows.append(
                f'<li class="quality-issue issue-{_escape(quality_issue.get("severity", "warning"))}"><strong>{_escape(quality_issue.get("category", "quality"))}: {_escape(quality_issue.get("message", "Issue detected."))}</strong><span>Suggested fix: {_escape(quality_issue.get("suggested_fix", "Inspect this job."))}</span></li>'
            )
        issues_html = "".join(issue_rows) or '<li class="quiet">No quality issues detected.</li>'
        approval_ready = "Yes — ready for human approval" if quality_report.get("approval_ready") is True else "No"
        export_ready = "Yes — approval gate satisfied" if quality_report.get("export_ready") is True else "No"
        quality_panel = f"""
<section class="panel quality-panel">
  <div class="panel-heading"><h2>Quality score</h2><span class="quality-badge quality-{_escape(quality_status)}">{_escape(overall_score)} · {_escape(quality_status)}</span></div>
  <div class="quality-summary">
    <div><span>Approval ready</span><strong>{_escape(approval_ready)}</strong></div>
    <div><span>Export ready</span><strong>{_escape(export_ready)}</strong></div>
    <div><span>Recommended action</span><strong>{_escape(quality_report.get("recommended_action", "inspect"))}</strong></div>
  </div>
  <div class="quality-grid">
    <div><h3>Category scores</h3><table><tbody>{category_rows}</tbody></table></div>
    <div><h3>Issues and suggested fixes</h3><ul class="quality-issues">{issues_html}</ul></div>
  </div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/score">
    <button class="score" type="submit">Re-score Job</button>
    <p class="quiet">Quality pass does not approve or export this job.</p>
  </form>
</section>"""
    if export_manifest is None:
        upload_kit_panel = """
<section class="panel upload-kit-panel">
  <div class="panel-heading"><h2>Manual upload kits</h2><span>Local only</span></div>
  <div class="upload-kit-content"><p>Create an approved export bundle before making upload kits.</p></div>
</section>"""
    elif upload_kit_preview is None:
        upload_kit_panel = f"""
<section class="panel upload-kit-panel">
  <div class="manual-only">MANUAL UPLOAD ONLY - NOT PUBLISHED</div>
  <div class="panel-heading"><h2>Manual upload kits</h2><span>Not created</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/upload-kit">
    <p>Create local formatting and checklists for YouTube Shorts, TikTok, and Instagram Reels.</p>
    <button class="upload-kit" type="submit">Create Manual Upload Kit</button>
    <p class="quiet">No API, login, browser automation, upload, or publishing occurs.</p>
  </form>
</section>"""
    else:
        kit_manifest = upload_kit_preview.get("manifest", {})
        if not isinstance(kit_manifest, dict):
            kit_manifest = {}
        manifest_json = _escape(json.dumps(kit_manifest, indent=2, ensure_ascii=False))
        platform_previews = upload_kit_preview.get("platforms", {})
        if not isinstance(platform_previews, dict):
            platform_previews = {}
        preview_sections = []
        for platform, preview in platform_previews.items():
            if not isinstance(preview, dict):
                continue
            metadata = preview.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            checklist = str(preview.get("checklist", "Checklist unavailable."))
            platform_dir = metadata.get("platform_dir", "local kit folder")
            preview_sections.append(
                f'<div class="platform-preview"><div class="panel-heading subheading"><h3>{_escape(platform.replace("_", " ").title())}</h3><span>{_escape(platform_dir)}</span></div><h4>Platform metadata</h4><pre>{_escape(json.dumps(metadata, indent=2, ensure_ascii=False))}</pre><h4>Upload checklist</h4><pre>{_escape(checklist)}</pre></div>'
            )
        previews_html = "".join(preview_sections) or '<div class="upload-kit-content"><p class="quiet">Platform previews are unavailable.</p></div>'
        upload_kit_panel = f"""
<section class="panel upload-kit-panel">
  <div class="manual-only">MANUAL UPLOAD ONLY - NOT PUBLISHED</div>
  <div class="panel-heading"><h2>Manual upload kits</h2><span>{len(platform_previews)} platforms</span></div>
  <div class="upload-kit-content"><p>Local folder: <code>{_escape(kit_manifest.get("upload_kit_dir", "exports/upload_kits"))}</code></p></div>
  <h3 class="section-label">Upload kit manifest</h3><pre>{manifest_json}</pre>
  {previews_html}
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/upload-kit">
    <button class="upload-kit" type="submit">Refresh Manual Upload Kit</button>
    <p class="quiet">Files remain local and require intentional human upload.</p>
  </form>
</section>"""
    body = f"""
<nav class="breadcrumb"><a href="/">← All jobs</a></nav>
<section class="job-title">
  <div><p class="eyebrow">Job detail</p><h1>{_escape(job.job_id)}</h1></div>
  {_state_badge(state)}
</section>
<section class="metadata-grid">
  <div><span>Status</span><strong>{_escape(job.status)}</strong></div>
  <div><span>Locale</span><strong>{_escape(job.locale)}</strong></div>
  <div><span>Mode</span><strong>{_escape(job.mode)}</strong></div>
  <div><span>Source</span><strong>{_escape(job.source)}</strong></div>
  <div class="wide"><span>Created</span><strong>{_escape(job.created_at)}</strong></div>
</section>
<section class="preview-grid">
  <article class="panel media-panel"><div class="panel-heading"><h2>Video</h2><span>{_escape(video_name or "missing")}</span></div>{video}</article>
  <article class="panel media-panel"><div class="panel-heading"><h2>Thumbnail</h2></div>{thumbnail}</article>
</section>
{quality_panel}
<section class="panel approval-panel">
  <div class="panel-heading"><h2>Approval</h2><span>Updated: {updated}</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/approval">
    <label for="notes">Review notes</label>
    <textarea id="notes" name="notes" rows="4" placeholder="Optional human note">{notes}</textarea>
    <div class="actions">
      <button class="approve" name="state" value="approved">Approve</button>
      <button class="reject" name="state" value="rejected">Reject</button>
      <button class="revise" name="state" value="needs_revision">Mark Needs Revision</button>
      <button class="reset" name="state" value="pending">Reset to Pending</button>
    </div>
  </form>
</section>
{revision_panel}
{export_panel}
{upload_kit_panel}
<section class="panel"><div class="panel-heading"><h2>Warnings</h2><span>{job.warning_count}</span></div><ul class="warnings">{warnings}</ul></section>
<section class="text-grid">
  <article class="panel"><div class="panel-heading"><h2>Script</h2></div><pre>{script}</pre></article>
  <article class="panel"><div class="panel-heading"><h2>Captions</h2></div><pre>{captions}</pre></article>
</section>
<section class="panel"><div class="panel-heading"><h2>Receipt</h2><span>receipt.json</span></div><pre>{receipt}</pre></section>
<section class="panel publisher-panel{publisher_class}">
  <div class="dry-run">{DRY_RUN_LABEL}</div>
  <div class="panel-heading"><h2>Publisher package</h2><span>{_escape(publisher_path.name if publisher_path else "not available")}</span></div>
  <pre>{publisher}</pre>
</section>"""
    return _page(f"Job {job.job_id}", body)


def render_error(status: int, message: str) -> str:
    body = f"""<section class="hero error-page"><p class="eyebrow">Error {status}</p><h1>{_escape(message)}</h1><p><a href="/">Return to Mission Control</a></p></section>"""
    return _page(f"Error {status}", body)
