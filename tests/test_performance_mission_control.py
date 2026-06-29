from __future__ import annotations

import http.client
import threading
from pathlib import Path

from content_factory.mission_control.app import create_server
from tests.test_performance_review import manual_entry, write_entries


def request(server, method: str, path: str) -> tuple[int, str, str | None]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), response.getheader("Location")
    finally:
        connection.close()


def start_server(tmp_path: Path, results_root: Path, performance_root: Path):
    server = create_server(
        tmp_path / "output", "127.0.0.1", 0, tmp_path / "exports",
        tmp_path / "templates", results_root, performance_root,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_mission_control_performance_page_handles_empty_results(tmp_path: Path):
    server, thread = start_server(tmp_path, tmp_path / "missing results", tmp_path / "performance reports")
    try:
        status, page, _ = request(server, "GET", "/performance")
        assert status == 200
        assert "No manual results recorded yet." in page
        assert "Generate Performance Review" in page
        assert "Performance" in request(server, "GET", "/")[1]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_mission_control_generates_and_shows_local_performance_review(tmp_path: Path):
    results_root = tmp_path / "results ledger"
    performance_root = tmp_path / "performance reports"
    write_entries(results_root, [manual_entry("entry", views=250, likes=25, leads=1)])
    server, thread = start_server(tmp_path, results_root, performance_root)
    try:
        status, page, _ = request(server, "GET", "/performance")
        assert status == 200
        assert "250" in page
        assert "script.default" in page
        assert "Recommended next manual experiment" in page
        forbidden = ("Fetch Metrics", "Sync YouTube", "Sync TikTok", "Sync Instagram", "OAuth", "Connect account")
        assert all(label not in page for label in forbidden)
        status, _, location = request(server, "POST", "/performance")
        assert status == 303
        assert location == "/performance"
        assert (performance_root / "PERFORMANCE_REVIEW.json").is_file()
        status, markdown, _ = request(server, "GET", "/performance/report")
        assert status == 200
        assert "# Local Performance Review" in markdown
        status, refreshed, _ = request(server, "GET", "/performance")
        assert status == 200
        assert "Open Performance Report" in refreshed
        assert ">Publish<" not in refreshed
        assert ">Post<" not in refreshed
        assert "Upload automatically" not in refreshed
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
