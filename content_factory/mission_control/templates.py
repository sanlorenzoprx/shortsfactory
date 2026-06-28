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


def render_index(jobs: list[JobRecord], approvals: dict[str, dict[str, object]]) -> str:
    rows = []
    for job in jobs:
        approval = approvals.get(job.job_id, {"state": "pending"})
        state = str(approval.get("state", "pending"))
        warning = (
            f'<span class="warning-count">{job.warning_count}</span>'
            if job.warning_count
            else '<span class="quiet">0</span>'
        )
        rows.append(
            f"""<tr>
  <td><a class="job-link" href="/jobs/{_url_job_id(job.job_id)}">{_escape(job.job_id)}</a></td>
  <td>{_state_badge(state)}</td>
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
        table_body = '<tr><td colspan="7" class="empty">No receipt-backed jobs found.</td></tr>'
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
      <thead><tr><th>Job</th><th>Approval</th><th>Status</th><th>Locale</th><th>Mode</th><th>Created</th><th>Warnings</th></tr></thead>
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
<section class="panel approval-panel">
  <div class="panel-heading"><h2>Approval</h2><span>Updated: {updated}</span></div>
  <form method="post" action="/jobs/{_url_job_id(job.job_id)}/approval">
    <label for="notes">Review notes</label>
    <textarea id="notes" name="notes" rows="4" placeholder="Optional human note">{notes}</textarea>
    <div class="actions">
      <button class="approve" name="state" value="approved">Approve</button>
      <button class="reject" name="state" value="rejected">Reject</button>
      <button class="revise" name="state" value="needs_revision">Needs Revision</button>
      <button class="reset" name="state" value="pending">Reset to Pending</button>
    </div>
  </form>
</section>
{export_panel}
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
