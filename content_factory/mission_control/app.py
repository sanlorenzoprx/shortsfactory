from __future__ import annotations

import argparse
import mimetypes
import re
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, unquote, urlsplit

from .approvals import APPROVAL_STATES, ApprovalStore
from .job_index import find_job, is_within, scan_jobs
from .templates import render_error, render_index, render_job_detail


MAX_FORM_BYTES = 64 * 1024
JOB_ROUTE = re.compile(r"^/jobs/([^/]+)$")
APPROVAL_ROUTE = re.compile(r"^/jobs/([^/]+)/approval$")
ARTIFACT_ROUTE = re.compile(r"^/artifacts/([^/]+)/([^/]+)$")
STATIC_ROOT = Path(__file__).with_name("static").resolve()


def _handler_class(output_root: Path) -> type[BaseHTTPRequestHandler]:
    approvals = ApprovalStore(output_root)

    class MissionControlHandler(BaseHTTPRequestHandler):
        server_version = "ShortsFactoryMissionControl/3A"

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/":
                jobs = scan_jobs(output_root)
                states = {job.job_id: approvals.read(job.job_id) for job in jobs}
                self._html(HTTPStatus.OK, render_index(jobs, states))
                return
            if path == "/static/mission_control.css":
                self._static_css()
                return
            job_match = JOB_ROUTE.fullmatch(path)
            if job_match:
                job_id = unquote(job_match.group(1))
                job = find_job(output_root, job_id)
                if job is None:
                    self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                    return
                self._html(HTTPStatus.OK, render_job_detail(job, approvals.read(job.job_id)))
                return
            artifact_match = ARTIFACT_ROUTE.fullmatch(path)
            if artifact_match:
                self._artifact(unquote(artifact_match.group(1)), unquote(artifact_match.group(2)))
                return
            self._html(HTTPStatus.NOT_FOUND, render_error(404, "Page not found"))

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            match = APPROVAL_ROUTE.fullmatch(path)
            if not match:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Page not found"))
                return
            job_id = unquote(match.group(1))
            job = find_job(output_root, job_id)
            if job is None:
                self._html(HTTPStatus.NOT_FOUND, render_error(404, "Job not found"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_FORM_BYTES:
                self._html(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, render_error(413, "Review form is too large"))
                return
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            state = form.get("state", [""])[0]
            notes = form.get("notes", [""])[0]
            if state not in APPROVAL_STATES:
                self._html(HTTPStatus.BAD_REQUEST, render_error(400, "Invalid approval state"))
                return
            approvals.write(job.job_id, state, notes)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/jobs/{job_match_id(job.job_id)}")
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
    output_root: str | Path = "output", host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer((host, port), _handler_class(root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the local-only Shorts Factory Mission Control review dashboard."
    )
    parser.add_argument("--output-root", default="output", help="Generated output root (default: output)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--open", action="store_true", help="Open the local dashboard in a browser")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = create_server(args.output_root, args.host, args.port)
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
