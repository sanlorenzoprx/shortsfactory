from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

from content_factory.compliance.compliance_renderer import (
    human_status,
    machine_status,
    status_label,
)

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
    <nav class="site-nav"><a href="/">Jobs</a><a href="/templates">Templates</a><a href="/performance">Performance</a><span class="local-badge">LOCAL ONLY</span></nav>
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


def _template_url(template_id: str) -> str:
    return quote(template_id, safe="")


def render_template_index(templates: list[dict[str, object]]) -> str:
    rows = []
    for template in templates:
        validation = template.get("validation", {})
        valid = bool(validation.get("valid")) if isinstance(validation, dict) else False
        status = "valid" if valid else "invalid"
        rows.append(
            f"""<tr>
  <td><a class="job-link" href="/templates/{_template_url(str(template.get('template_id', '')))}">{_escape(template.get('template_id', ''))}</a></td>
  <td>{_escape(template.get('template_type', ''))}</td><td>{_escape(template.get('name', ''))}</td>
  <td>{_escape(template.get('source', ''))}</td><td>{_escape(template.get('version', ''))}</td>
  <td>{_escape(template.get('updated_at', ''))}</td><td><span class="quality-badge quality-{'pass' if valid else 'fail'}">{status}</span></td>
  <td class="hash-cell">{_escape(template.get('template_version_hash', ''))}</td>
</tr>"""
        )
    body = f"""<section class="hero"><p class="eyebrow">Local creative control</p><h1>Template Editor</h1>
<p>View, validate, version, restore, and preview text-only templates. Templates never execute code or publish.</p></section>
<section class="panel"><div class="panel-heading"><h2>Templates</h2><span>{len(templates)} local/built-in assets</span></div>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Source</th><th>Version</th><th>Updated</th><th>Validation</th><th>Hash</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>"""
    return _page("Template Editor", body)


def render_template_detail(
    template: dict[str, object],
    history: list[dict[str, str]],
    *,
    raw_json: str | None = None,
    validation: dict[str, object] | None = None,
    preview: str | None = None,
    message: str | None = None,
) -> str:
    template_id = str(template.get("template_id", ""))
    raw = raw_json if raw_json is not None else json.dumps(template, indent=2, ensure_ascii=False)
    current_validation = validation or template.get("validation") or {}
    validation_text = json.dumps(current_validation, indent=2, ensure_ascii=False)
    history_items = []
    for revision in history:
        history_id = revision.get("history_id", "")
        history_items.append(
            f'<li><code>{_escape(history_id)}</code><form class="inline-form" method="post" action="/templates/{_template_url(template_id)}/restore"><input type="hidden" name="history_id" value="{_escape(history_id)}"><button type="submit" class="reset">Restore as new version</button></form></li>'
        )
    history_html = "".join(history_items) or '<li class="quiet">No saved history yet.</li>'
    preview_html = f'<section class="panel"><div class="panel-heading"><h2>Preview</h2><span>fixed sample context</span></div><pre>{_escape(preview)}</pre></section>' if preview is not None else ""
    message_html = f'<p class="template-message">{_escape(message)}</p>' if message else ""
    locked = bool(template.get("locked"))
    save_disabled = " disabled" if locked else ""
    body = f"""<section class="hero"><p class="eyebrow"><a href="/templates">Template Editor</a> / {_escape(template_id)}</p>
<h1>{_escape(template.get('name', template_id))}</h1><p>{_escape(template.get('description', ''))}</p>{message_html}</section>
<section class="panel"><div class="panel-heading"><h2>Edit JSON</h2><span>v{_escape(template.get('version', ''))} · {_escape(template.get('template_version_hash', ''))}</span></div>
<p>Text only. Known placeholders use <code>{{name}}</code>. Expressions, filters, code, and path traversal are rejected.</p>
<form method="post"><textarea class="json-editor" name="template_json" rows="28" spellcheck="false">{_escape(raw)}</textarea>
<div class="actions">
<button formaction="/templates/{_template_url(template_id)}/validate" type="submit">Validate</button>
<button formaction="/templates/{_template_url(template_id)}/preview" type="submit">Preview</button>
<button formaction="/templates/{_template_url(template_id)}/save" type="submit" class="approve"{save_disabled}>Save new version</button>
</div></form>{'<p class="warning-count">Locked built-in: save and restore are disabled.</p>' if locked else ''}</section>
<section class="text-grid"><article class="panel"><div class="panel-heading"><h2>Validation</h2></div><pre>{_escape(validation_text)}</pre></article>
<article class="panel"><div class="panel-heading"><h2>History</h2><span>{len(history)} revisions</span></div><ul class="template-history">{history_html}</ul></article></section>
{preview_html}"""
    return _page(f"Template {template_id}", body)


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
    preview_manifest: dict[str, object] | None = None,
    compliance_checklist: dict[str, object] | None = None,
    results_entries: list[dict[str, object]] | None = None,
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
    template_usage = job.receipt.get("templates", {})
    if not isinstance(template_usage, dict):
        template_usage = {}
    template_usage_panel = ""
    if template_usage:
        template_usage_panel = f'<section class="panel"><div class="panel-heading"><h2>Template usage</h2><span>recorded in receipt</span></div><pre>{_escape(json.dumps(template_usage, indent=2, ensure_ascii=False))}</pre></section>'
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
    if upload_kit_preview is None:
        publisher_preview_panel = ""
    elif preview_manifest is None:
        publisher_preview_panel = f"""
<section class="panel publisher-preview-panel">
  <div class="manual-only">MANUAL REVIEW ONLY - NOT PUBLISHED</div>
  <div class="panel-heading"><h2>Publisher preview cards</h2><span>Not generated</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/preview-cards">
    <p>Generate static local HTML and text previews from the approved manual upload kit.</p>
    <button class="preview-cards" type="submit">Generate Preview Cards</button>
    <p class="quiet">Preview only. No API, account connection, upload, or publishing occurs.</p>
  </form>
</section>"""
    else:
        platforms = preview_manifest.get("platforms", {})
        if not isinstance(platforms, dict):
            platforms = {}
        links = []
        for platform in ("youtube_shorts", "tiktok", "instagram_reels"):
            details = platforms.get(platform, {})
            if not isinstance(details, dict):
                continue
            filename = str(details.get("preview_html", ""))
            if filename:
                label = platform.replace("_", " ").title()
                links.append(f'<a class="preview-link" href="/previews/{_url_job_id(job.job_id)}/{quote(filename, safe="")}" target="_blank" rel="noopener">Open {label} Preview</a>')
        links.append(f'<a class="preview-link" href="/previews/{_url_job_id(job.job_id)}/PREVIEW_MANIFEST.json" target="_blank" rel="noopener">Open Preview Manifest</a>')
        publisher_preview_panel = f"""
<section class="panel publisher-preview-panel">
  <div class="manual-only">MANUAL REVIEW ONLY - NOT PUBLISHED</div>
  <div class="panel-heading"><h2>Publisher preview cards</h2><span>Ready for manual review</span></div>
  <div class="preview-card-links">{''.join(links)}</div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/preview-cards">
    <button class="preview-cards" type="submit">Refresh Preview Cards</button>
    <p class="quiet">Static local previews only. Human upload remains required.</p>
  </form>
</section>"""
    if upload_kit_preview is None or preview_manifest is None:
        compliance_panel = ""
    elif compliance_checklist is None:
        compliance_panel = f"""
<section class="panel compliance-panel">
  <div class="manual-only">FINAL HUMAN GATE - MANUAL UPLOAD ONLY</div>
  <div class="panel-heading"><h2>Final compliance checklist</h2><span>Not generated</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/compliance">
    <p>Generate the final local compliance checklist after preview cards are ready.</p>
    <button class="compliance" type="submit">Generate Compliance Checklist</button>
    <p class="quiet">This is a local review gate only. No account connection or upload action exists here.</p>
  </form>
</section>"""
    else:
        compliance_status = status_label(str(compliance_checklist.get("status", "needs_human_review")))
        compliance_machine = machine_status(compliance_checklist)
        compliance_human = human_status(compliance_checklist)
        advisory_items = compliance_checklist.get("warnings", [])
        if not isinstance(advisory_items, list):
            advisory_items = []
        warning_rows = []
        for advisory in advisory_items:
            if isinstance(advisory, dict):
                warning_rows.append(f"<li>{_escape(advisory.get('message', 'Warning'))}</li>")
            else:
                warning_rows.append(f"<li>{_escape(advisory)}</li>")
        warning_html = "".join(warning_rows) or '<li class="quiet">No advisory warnings recorded.</li>'
        if compliance_checklist.get("ready_for_manual_upload") is True:
            review_action = '<p class="quiet compliance-ready-note">This job is ready for manual upload only. Shorts Factory still has not published anything.</p>'
        else:
            review_action = f"""
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/compliance/review">
    <button class="compliance" type="submit">Mark Reviewed for Manual Upload</button>
    <p class="quiet">Explicit local human confirmation only. This never publishes or uploads.</p>
  </form>"""
        compliance_panel = f"""
<section class="panel compliance-panel">
  <div class="manual-only">FINAL HUMAN GATE - MANUAL UPLOAD ONLY</div>
  <div class="panel-heading"><h2>Final compliance checklist</h2><span class="quality-badge quality-{_escape(compliance_machine)}">{_escape(compliance_status)}</span></div>
  <div class="quality-summary">
    <div><span>Compliance status</span><strong>{_escape(compliance_status)}</strong></div>
    <div><span>Machine checks</span><strong>{_escape(compliance_machine)}</strong></div>
    <div><span>Human review</span><strong>{_escape(compliance_human)}</strong></div>
  </div>
  <div class="preview-card-links">
    <a class="preview-link" href="/compliance/{_url_job_id(job.job_id)}/COMPLIANCE_CHECKLIST.md" target="_blank" rel="noopener">Open Compliance Checklist</a>
    <a class="preview-link" href="/compliance/{_url_job_id(job.job_id)}/COMPLIANCE_CHECKLIST.json" target="_blank" rel="noopener">Open Compliance JSON</a>
  </div>
  <h3 class="section-label">Advisory warnings</h3>
  <ul class="warnings">{warning_html}</ul>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/compliance">
    <button class="compliance" type="submit">Refresh Compliance Checklist</button>
    <p class="quiet">Refresh re-runs local deterministic checks only.</p>
  </form>
  {review_action}
</section>"""
    if compliance_checklist is None or compliance_checklist.get("ready_for_manual_upload") is not True:
        results_panel = """
<section class="panel results-panel">
  <div class="manual-only">MANUAL ENTRY ONLY</div>
  <div class="panel-heading"><h2>Results ledger</h2><span>Unavailable</span></div>
  <div class="upload-kit-content"><p>Results Ledger unavailable until compliance is Ready for Manual Upload.</p></div>
</section>"""
    else:
        entries = results_entries or []
        rows = []
        latest = entries[0] if entries else None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            metrics = entry.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            rows.append(
                f"<tr><td>{_escape(entry.get('platform', ''))}</td><td><a href=\"{_escape(entry.get('manual_upload_url', ''))}\" target=\"_blank\" rel=\"noopener\">{_escape(entry.get('manual_upload_url', ''))}</a></td><td>{_escape(metrics.get('views', 0))}</td><td>{_escape(metrics.get('likes', 0))}</td><td>{_escape(metrics.get('comments', 0))}</td><td>{_escape(metrics.get('shares', 0))}</td><td>{_escape(metrics.get('saves', 0))}</td><td>{_escape(metrics.get('leads', 0))}</td><td>{_escape(entry.get('notes', ''))}</td></tr>"
            )
        entries_table = (
            f"""<div class="table-wrap"><table><thead><tr><th>Platform</th><th>Manual URL</th><th>Views</th><th>Likes</th><th>Comments</th><th>Shares</th><th>Saves</th><th>Leads</th><th>Notes</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""
            if rows
            else '<div class="upload-kit-content"><p class="quiet">No manual results recorded yet.</p></div>'
        )
        form_label = "Update Manual Result" if latest is not None else "Record Manual Result"
        latest_metrics = latest.get("metrics", {}) if isinstance(latest, dict) else {}
        if not isinstance(latest_metrics, dict):
            latest_metrics = {}
        entry_id_input = (
            f'<input type="hidden" name="entry_id" value="{_escape(latest.get("entry_id", ""))}">'
            if isinstance(latest, dict)
            else ""
        )
        platform_value = _escape(latest.get("platform", "youtube_shorts")) if isinstance(latest, dict) else "youtube_shorts"
        url_value = _escape(latest.get("manual_upload_url", "")) if isinstance(latest, dict) else ""
        notes_value = _escape(latest.get("notes", "")) if isinstance(latest, dict) else ""
        results_panel = f"""
<section class="panel results-panel">
  <div class="manual-only">MANUAL ENTRY ONLY</div>
  <div class="panel-heading"><h2>Results ledger</h2><span>{_escape(str(len(rows)))} entries</span></div>
  <div class="preview-card-links">
    <a class="preview-link" href="/results/summary" target="_blank" rel="noopener">Open Results Summary</a>
  </div>
  {entries_table}
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/results">
    {entry_id_input}
    <label for="results-platform">Platform</label>
    <select id="results-platform" name="platform">
      <option value="youtube_shorts"{' selected' if platform_value == 'youtube_shorts' else ''}>youtube_shorts</option>
      <option value="tiktok"{' selected' if platform_value == 'tiktok' else ''}>tiktok</option>
      <option value="instagram_reels"{' selected' if platform_value == 'instagram_reels' else ''}>instagram_reels</option>
      <option value="other"{' selected' if platform_value == 'other' else ''}>other</option>
    </select>
    <label for="results-url">Manual URL</label>
    <input id="results-url" name="url" type="url" value="{url_value}" placeholder="https://example.com/manual-upload" required>
    <div class="results-grid">
      <label>Views<input name="views" type="number" min="0" value="{_escape(latest_metrics.get('views', 0))}"></label>
      <label>Likes<input name="likes" type="number" min="0" value="{_escape(latest_metrics.get('likes', 0))}"></label>
      <label>Comments<input name="comments" type="number" min="0" value="{_escape(latest_metrics.get('comments', 0))}"></label>
      <label>Shares<input name="shares" type="number" min="0" value="{_escape(latest_metrics.get('shares', 0))}"></label>
      <label>Saves<input name="saves" type="number" min="0" value="{_escape(latest_metrics.get('saves', 0))}"></label>
      <label>Leads<input name="leads" type="number" min="0" value="{_escape(latest_metrics.get('leads', 0))}"></label>
    </div>
    <label for="results-notes">Notes</label>
    <textarea id="results-notes" name="notes" rows="3" placeholder="Manual upload notes">{notes_value}</textarea>
    <button class="results" type="submit">{form_label}</button>
    <p class="quiet">Manual entry only. No metric fetching, sync, scraping, upload, or publishing occurs.</p>
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
{publisher_preview_panel}
{compliance_panel}
{results_panel}
<section class="panel"><div class="panel-heading"><h2>Warnings</h2><span>{job.warning_count}</span></div><ul class="warnings">{warnings}</ul></section>
<section class="text-grid">
  <article class="panel"><div class="panel-heading"><h2>Script</h2></div><pre>{script}</pre></article>
  <article class="panel"><div class="panel-heading"><h2>Captions</h2></div><pre>{captions}</pre></article>
</section>
{template_usage_panel}
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


def render_performance_review(
    review: dict[str, object],
    *,
    report_exists: bool,
    report_path: Path,
) -> str:
    totals = review.get("totals", {})
    rates = review.get("rates", {})
    top_jobs = review.get("top_jobs", [])
    platforms = review.get("platform_summary", {})
    templates = review.get("template_summary", {})
    recommendations = review.get("recommendations", [])
    if not isinstance(totals, dict):
        totals = {}
    if not isinstance(rates, dict):
        rates = {}
    if not isinstance(top_jobs, list):
        top_jobs = []
    if not isinstance(platforms, dict):
        platforms = {}
    if not isinstance(templates, dict):
        templates = {}
    if not isinstance(recommendations, list):
        recommendations = []
    job_rows = []
    for index, row in enumerate(top_jobs, 1):
        if not isinstance(row, dict):
            continue
        job_rows.append(
            f"<tr><td>{index}</td><td>{_escape(row.get('job_id', ''))}</td><td>{_escape(row.get('platform', ''))}</td><td>{_escape(row.get('views', 0))}</td><td>{_escape(row.get('likes', 0))}</td><td>{_escape(row.get('leads', 0))}</td><td>{_escape(row.get('quality_score', 'Not available'))}</td></tr>"
        )
    if not job_rows:
        job_rows.append('<tr><td colspan="7" class="empty">No manual results recorded yet.</td></tr>')
    platform_rows = []
    for platform, row in platforms.items():
        if not isinstance(row, dict):
            continue
        like_rate = f"{float(row.get('like_rate', 0)):.2%}"
        platform_rows.append(
            f"<tr><td>{_escape(platform)}</td><td>{_escape(row.get('entries', 0))}</td><td>{_escape(row.get('views', 0))}</td><td>{_escape(row.get('likes', 0))}</td><td>{_escape(row.get('leads', 0))}</td><td>{_escape(like_rate)}</td></tr>"
        )
    if not platform_rows:
        platform_rows.append('<tr><td colspan="6" class="empty">No platform signals yet.</td></tr>')
    template_rows = []
    for template, row in templates.items():
        if not isinstance(row, dict):
            continue
        template_rows.append(
            f"<tr><td>{_escape(template)}</td><td>{_escape(row.get('entries', 0))}</td><td>{_escape(row.get('views', 0))}</td><td>{_escape(row.get('likes', 0))}</td><td>{_escape(row.get('leads', 0))}</td></tr>"
        )
    if not template_rows:
        template_rows.append('<tr><td colspan="5" class="empty">No template signals yet.</td></tr>')
    recommendation = "Record at least one manual result before choosing the next experiment."
    if recommendations and isinstance(recommendations[0], dict):
        recommendation = str(recommendations[0].get("message", recommendation))
    status = str(review.get("status", "empty"))
    empty = ""
    if status == "empty":
        empty = '<div class="upload-kit-content"><p>No manual results recorded yet.<br>Record a result with results_ledger.py before reviewing performance.</p></div>'
    total_like_rate = f"{float(rates.get('like_rate', 0)):.2%}"
    report_link = (
        '<a class="preview-link" href="/performance/report" target="_blank" rel="noopener">Open Performance Report</a>'
        if report_exists
        else '<span class="quiet">Generate the report to open the Markdown file.</span>'
    )
    body = f"""
<section class="hero">
  <p class="eyebrow">Manual local signals</p>
  <h1>Performance Review</h1>
  <p>Decision support from manually entered local results. No network collection or publishing occurs.</p>
</section>
<section class="panel performance-overview">
  <div class="manual-only">MANUAL RESULTS ONLY</div>
  <div class="panel-heading"><h2>Status</h2><span class="state state-{_escape(status)}">{_escape(status.title())}</span></div>
  {empty}
  <div class="quality-summary">
    <div><span>Entries</span><strong>{_escape(totals.get('entries', 0))}</strong></div>
    <div><span>Platforms</span><strong>{_escape(totals.get('platforms', 0))}</strong></div>
    <div><span>Views</span><strong>{_escape(totals.get('views', 0))}</strong></div>
    <div><span>Likes</span><strong>{_escape(totals.get('likes', 0))}</strong></div>
    <div><span>Leads</span><strong>{_escape(totals.get('leads', 0))}</strong></div>
    <div><span>Like rate</span><strong>{_escape(total_like_rate)}</strong></div>
  </div>
  <div class="preview-card-links">{report_link}<a class="preview-link" href="/results/summary" target="_blank" rel="noopener">View Manual Results Summary</a></div>
  <p class="quiet">Report path: {_escape(report_path)}</p>
  <form method="post" action="/performance"><button class="performance" type="submit">Generate Performance Review</button></form>
</section>
<section class="panel"><div class="panel-heading"><h2>Best jobs</h2><span>Local ranking</span></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Job</th><th>Platform</th><th>Views</th><th>Likes</th><th>Leads</th><th>Quality</th></tr></thead><tbody>{''.join(job_rows)}</tbody></table></div></section>
<section class="panel"><div class="panel-heading"><h2>Platform summary</h2></div><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Entries</th><th>Views</th><th>Likes</th><th>Leads</th><th>Like rate</th></tr></thead><tbody>{''.join(platform_rows)}</tbody></table></div></section>
<section class="panel"><div class="panel-heading"><h2>Template signals</h2></div><div class="table-wrap"><table><thead><tr><th>Template</th><th>Entries</th><th>Views</th><th>Likes</th><th>Leads</th></tr></thead><tbody>{''.join(template_rows)}</tbody></table></div></section>
<section class="panel recommendation-panel"><div class="panel-heading"><h2>Recommended next manual experiment</h2></div><div class="upload-kit-content"><p>{_escape(recommendation)}</p></div></section>"""
    return _page("Performance Review", body)
