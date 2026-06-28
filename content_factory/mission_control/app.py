from __future__ import annotations

import argparse
import json
import mimetypes
import re
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, unquote, urlsplit

from content_factory.exporting.bundle_exporter import BundleExportError, export_approved_bundle
from content_factory.exporting.manifest import read_export_manifest
from content_factory.quality.quality_scorer import QualityScoringError, score_job
from content_factory.quality.quality_store import QualityStore, QualityStoreError
from content_factory.revisions.revision_manifest import read_revision_manifest
from content_factory.revisions.revision_queue import RevisionQueue, RevisionTaskError
from content_factory.revisions.revision_runner import RevisionRunError, run_revision
from content_factory.upload_kits.kit_builder import (
    UploadKitError,
    build_upload_kit,
    load_upload_kit_preview,
)
from content_factory.templates import TemplateRenderError, TemplateStore, TemplateStoreError, render_template, validate_template_json

from .approvals import APPROVAL_STATES, ApprovalStore
from .job_index import find_job, is_within, scan_jobs
from .templates import render_error, render_index, render_job_detail, render_template_detail, render_template_index


MAX_FORM_BYTES = 64 * 1024
JOB_ROUTE = re.compile(r"^/jobs/([^/]+)$")
APPROVAL_ROUTE = re.compile(r"^/jobs/([^/]+)/approval$")
EXPORT_ROUTE = re.compile(r"^/jobs/([^/]+)/export$")
REVISION_TASK_ROUTE = re.compile(r"^/jobs/([^/]+)/revision-task$")
RUN_REVISION_ROUTE = re.compile(r"^/jobs/([^/]+)/run-revision$")
QUALITY_ROUTE = re.compile(r"^/jobs/([^/]+)/score$")
UPLOAD_KIT_ROUTE = re.compile(r"^/jobs/([^/]+)/upload-kit$")
TEMPLATE_ROUTE = re.compile(r"^/templates/([^/]+)$")
TEMPLATE_ACTION_ROUTE = re.compile(r"^/templates/([^/]+)/(validate|preview|save|restore)$")
ARTIFACT_ROUTE = re.compile(r"^/artifacts/([^/]+)/([^/]+)$")
STATIC_ROOT = Path(__file__).with_name("static").resolve()
TEMPLATE_SAMPLE_CONTEXT = {
    "job_id": "sample", "idea": "AI tool that tests startup ideas before builders waste months",
    "hook": "Would this idea survive the ghost town test?", "verdict_headline": "Promising, but distribution is the risk",
    "lit_score": 78, "risk_level": "medium", "top_reason": "The pain is real, but the buyer path needs proof.",
    "next_step": "Test one landing page with ten builders.", "source": "sample", "locale": "en-US",
    "cta": "Run your idea through the test before you build.", "created_at": "2026-06-28T00:00:00+00:00",
    "platform": "youtube_shorts", "hashtags": "#shorts #startup #ideavalidation", "title": "Would this idea survive?",
    "caption": "Promising, but distribution is the risk.", "description": "A deterministic sample description.",
    "revision_note": "Make the hook clearer.", "original_job_id": "sample-original", "quality_score": 88,
    "quality_status": "pass", "recommended_action": "approve",
}


def _handler_class(output_root: Path, export_root: Path, template_root: Path) -> type[BaseHTTPRequestHandler]:
    approvals = ApprovalStore(output_root)
    revisions = RevisionQueue(output_root)
    quality = QualityStore(output_root)
    template_store = TemplateStore(template_root)

    class MissionControlHandler(BaseHTTPRequestHandler):
        server_version = "ShortsFactoryMissionControl/3F"

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/":
                jobs = scan_jobs(output_root)
                states = {job.job_id: approvals.read(job.job_id) for job in jobs}
                try:
                    reports = {job.job_id: quality.read(job.job_id) for job in jobs}
                except QualityStoreError as exc:
                    self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                    return
                self._html(HTTPStatus.OK, render_index(jobs, states, reports))
                return
            if path == "/static/mission_control.css":
                self._static_css()
                return
            if path == "/templates":
                self._html(HTTPStatus.OK, render_template_index(template_store.list()))
                return
            template_match = TEMPLATE_ROUTE.fullmatch(path)
            if template_match:
                template_id = unquote(template_match.group(1))
                try:
                    template = template_store.get(template_id)
                    if template is None:
                        raise TemplateStoreError(f"template not found: {template_id}")
                    validation = template_store.validate(template_id)
                    history = template_store.history(template_id)
                except TemplateStoreError as exc:
                    self._html(HTTPStatus.NOT_FOUND, render_error(404, str(exc)))
                    return
                self._html(HTTPStatus.OK, render_template_detail(template, history, validation=validation))
                return
            job_match = JOB_ROUTE.fullmatch(path)
            if job_match:
                job_id = unquote(job_match.group(1))
                job = find_job(output_root, job_id)
                if job is None:
                    self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                    return
                export_manifest = read_export_manifest(export_root, job.job_id)
                try:
                    revision_task = revisions.read(job.job_id)
                except RevisionTaskError as exc:
                    self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                    return
                revision_manifest = read_revision_manifest(
                    job.artifacts.get("REVISION_MANIFEST.json")
                )
                try:
                    quality_report = quality.read(job.job_id)
                except QualityStoreError as exc:
                    self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                    return
                try:
                    upload_kit_preview = load_upload_kit_preview(export_root, job.job_id)
                except UploadKitError as exc:
                    self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                    return
                self._html(
                    HTTPStatus.OK,
                    render_job_detail(
                        job,
                        approvals.read(job.job_id),
                        export_manifest,
                        revision_task,
                        revision_manifest,
                        quality_report,
                        upload_kit_preview,
                    ),
                )
                return
            artifact_match = ARTIFACT_ROUTE.fullmatch(path)
            if artifact_match:
                self._artifact(unquote(artifact_match.group(1)), unquote(artifact_match.group(2)))
                return
            self._html(HTTPStatus.NOT_FOUND, render_error(404, "Page not found"))

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            template_action = TEMPLATE_ACTION_ROUTE.fullmatch(path)
            if template_action:
                self._template_action(unquote(template_action.group(1)), template_action.group(2))
                return
            match = APPROVAL_ROUTE.fullmatch(path)
            if not match:
                export_match = EXPORT_ROUTE.fullmatch(path)
                if export_match:
                    self._export(unquote(export_match.group(1)))
                else:
                    revision_task_match = REVISION_TASK_ROUTE.fullmatch(path)
                    run_revision_match = RUN_REVISION_ROUTE.fullmatch(path)
                    quality_match = QUALITY_ROUTE.fullmatch(path)
                    upload_kit_match = UPLOAD_KIT_ROUTE.fullmatch(path)
                    if revision_task_match:
                        self._create_revision_task(unquote(revision_task_match.group(1)))
                    elif run_revision_match:
                        self._run_revision(unquote(run_revision_match.group(1)))
                    elif quality_match:
                        self._score_job(unquote(quality_match.group(1)))
                    elif upload_kit_match:
                        self._build_upload_kit(unquote(upload_kit_match.group(1)))
                    else:
                        self._html(HTTPStatus.NOT_FOUND, render_error(404, "Page not found"))
                return
            job_id = unquote(match.group(1))
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            form = self._read_form()
            if form is None:
                return
            state = form.get("state", [""])[0]
            notes = form.get("notes", [""])[0]
            if state not in APPROVAL_STATES:
                self._html(HTTPStatus.BAD_REQUEST, render_error(400, "Invalid approval state"))
                return
            approvals.write(job.job_id, state, notes)
            self._redirect_to_job(job.job_id)

        def _export(self, job_id: str) -> None:
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            try:
                export_approved_bundle(job.job_id, output_root, export_root)
            except (BundleExportError, OSError) as exc:
                self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/jobs/{job_match_id(job.job_id)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _create_revision_task(self, job_id: str) -> None:
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            form = self._read_form()
            if form is None:
                return
            note = form.get("revision_note", [""])[0]
            try:
                revisions.create(job.job_id, note)
                approvals.write(job.job_id, "needs_revision", note)
            except (RevisionTaskError, ValueError, OSError) as exc:
                self._html(HTTPStatus.BAD_REQUEST, render_error(400, str(exc)))
                return
            self._redirect_to_job(job.job_id)

        def _run_revision(self, job_id: str) -> None:
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            try:
                run_revision(job.job_id, output_root, template_root=template_root)
            except (RevisionRunError, OSError) as exc:
                self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                return
            self._redirect_to_job(job.job_id)

        def _score_job(self, job_id: str) -> None:
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            try:
                score_job(job.job_id, output_root)
            except (QualityScoringError, OSError) as exc:
                self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                return
            self._redirect_to_job(job.job_id)

        def _build_upload_kit(self, job_id: str) -> None:
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            try:
                build_upload_kit(job.job_id, export_root, "all", template_root)
            except (UploadKitError, OSError) as exc:
                self._html(HTTPStatus.CONFLICT, render_error(409, str(exc)))
                return
            self._redirect_to_job(job.job_id)

        def _template_action(self, template_id: str, action: str) -> None:
            try:
                current = template_store.get(template_id)
                if current is None:
                    raise TemplateStoreError(f"template not found: {template_id}")
            except TemplateStoreError as exc:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, str(exc)))
                return
            form = self._read_form()
            if form is None:
                return
            try:
                if action == "restore":
                    template_store.restore(template_id, form.get("history_id", [""])[0])
                    self._redirect_to_template(template_id)
                    return
                raw = form.get("template_json", [""])[0]
                validation = validate_template_json(raw)
                try:
                    candidate = json.loads(raw)
                except json.JSONDecodeError:
                    candidate = None
                if action == "validate":
                    self._html(
                        HTTPStatus.OK if validation["valid"] else HTTPStatus.BAD_REQUEST,
                        render_template_detail(current, template_store.history(template_id), raw_json=raw, validation=validation, message="Template is valid." if validation["valid"] else "Template validation failed."),
                    )
                    return
                if not validation["valid"] or not isinstance(candidate, dict):
                    raise TemplateStoreError("Invalid template: " + "; ".join(validation["errors"]))
                if candidate.get("template_id") != template_id:
                    raise TemplateStoreError("template_id cannot be changed")
                if action == "preview":
                    rendered = render_template(candidate, TEMPLATE_SAMPLE_CONTEXT)
                    preview = "\n".join(rendered) if isinstance(rendered, list) else rendered
                    self._html(HTTPStatus.OK, render_template_detail(current, template_store.history(template_id), raw_json=raw, validation=validation, preview=preview, message="Preview uses fixed local sample data."))
                    return
                if action == "save":
                    template_store.save(template_id, candidate)
                    self._redirect_to_template(template_id)
                    return
                raise TemplateStoreError("unknown template action")
            except (TemplateStoreError, TemplateRenderError, OSError) as exc:
                validation = validate_template_json(form.get("template_json", [json.dumps(current)])[0])
                self._html(HTTPStatus.BAD_REQUEST, render_template_detail(current, template_store.history(template_id), raw_json=form.get("template_json", [None])[0], validation=validation, message=str(exc)))

        def _redirect_to_template(self, template_id: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/templates/{job_match_id(template_id)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _read_form(self) -> dict[str, list[str]] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_FORM_BYTES:
                self._html(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    render_error(413, "Review form is too large"),
                )
                return None
            try:
                body = self.rfile.read(length).decode("utf-8")
            except UnicodeDecodeError:
                self._html(HTTPStatus.BAD_REQUEST, render_error(400, "Invalid form encoding"))
                return None
            return parse_qs(body, keep_blank_values=True)

        def _redirect_to_job(self, job_id: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/jobs/{job_match_id(job_id)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _artifact(self, job_id: str, artifact_name: str) -> None:
            job = find_job(output_root, job_id)
            if job is None or artifact_name not in job.artifacts:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Artifact not found"))
                return
            path = job.artifacts[artifact_name]
            if not path.is_file() or not is_within(path, output_root):
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Artifact not found"))
                return
            try:
                size = path.stat().st_size
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", "inline")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with path.open("rb") as handle:
                    while chunk := handle.read(64 * 1024):
                        self.wfile.write(chunk)
            except OSError:
                if not self.wfile.closed:
                    self.close_connection = True

        def _static_css(self) -> None:
            path = STATIC_ROOT / "mission_control.css"
            if not path.is_file() or not is_within(path, STATIC_ROOT):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionError):
                self.close_connection = True

        def _html(self, status: HTTPStatus, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self'; img-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionError):
                self.close_connection = True

        def log_message(self, format: str, *args: object) -> None:
            print(f"[{self.log_date_time_string()}] {format % args}")

    return MissionControlHandler


def job_match_id(job_id: str) -> str:
    from urllib.parse import quote

    return quote(job_id, safe="")


def create_server(
    output_root: str | Path = "output",
    host: str = "127.0.0.1",
    port: int = 8765,
    export_root: str | Path = "exports",
    template_root: str | Path = "templates",
) -> ThreadingHTTPServer:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    exports = Path(export_root).expanduser().resolve()
    templates = Path(template_root).expanduser().resolve()
    return ThreadingHTTPServer((host, port), _handler_class(root, exports, templates))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the local-only Shorts Factory Mission Control review dashboard."
    )
    parser.add_argument("--output-root", default="output", help="Generated output root (default: output)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--export-root", default="exports", help="Local export root (default: exports)")
    parser.add_argument("--template-root", default="templates", help="Local template root (default: templates)")
    parser.add_argument("--open", action="store_true", help="Open the local dashboard in a browser")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = create_server(args.output_root, args.host, args.port, args.export_root, args.template_root)
    url = f"http://{args.host}:{server.server_port}"
    print(f"Mission Control running at {url}", flush=True)
    print("Local review only. Live publishing is disabled.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMission Control stopped.")
    finally:
        server.server_close()
    return 0
