import http.client
import json
import threading
from pathlib import Path
from urllib.parse import urlencode

from content_factory.mission_control.app import create_server
from content_factory.templates import TemplateStore


def request(server, method: str, path: str, fields: dict[str, str] | None = None):
    body = urlencode(fields or {}).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8"), response.getheader("Location")
    finally:
        connection.close()


def running_server(tmp_path: Path):
    server = create_server(tmp_path / "output", "127.0.0.1", 0, tmp_path / "exports", tmp_path / "templates")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_mission_control_lists_templates_and_previews_sample_context(tmp_path: Path):
    server, thread = running_server(tmp_path)
    try:
        status, page, _ = request(server, "GET", "/templates")
        assert status == 200
        assert "script.default" in page
        assert "Template Editor" in page
        template = TemplateStore(tmp_path / "templates").get("script.default")
        status, preview, _ = request(server, "POST", "/templates/script.default/preview", {"template_json": json.dumps(template)})
        assert status == 200
        assert "Would this idea survive the ghost town test?" in preview
        assert "fixed sample context" in preview
    finally:
        stop(server, thread)


def test_mission_control_save_writes_version_and_history(tmp_path: Path):
    server, thread = running_server(tmp_path)
    store = TemplateStore(tmp_path / "templates")
    try:
        template = store.get("script.default")
        template["name"] = "Mission Control edit"
        status, _, location = request(server, "POST", "/templates/script.default/save", {"template_json": json.dumps(template)})
        assert status == 303
        assert location == "/templates/script.default"
        assert store.get("script.default")["version"] == 2
        assert len(store.history("script.default")) == 1
    finally:
        stop(server, thread)


def test_mission_control_rejects_invalid_template_save(tmp_path: Path):
    server, thread = running_server(tmp_path)
    store = TemplateStore(tmp_path / "templates")
    try:
        template = store.get("script.default")
        template["content"].append("{exec}")
        template["optional_placeholders"].append("exec")
        status, page, _ = request(server, "POST", "/templates/script.default/save", {"template_json": json.dumps(template)})
        assert status == 400
        assert "Forbidden placeholders" in page
        assert store.get("script.default")["version"] == 1
    finally:
        stop(server, thread)


def test_template_html_is_escaped_and_never_executed(tmp_path: Path):
    store = TemplateStore(tmp_path / "templates")
    template = store.get("script.default")
    template["content"][0] = "<script>alert('x')</script> {hook}"
    store.save("script.default", template)
    server, thread = running_server(tmp_path)
    try:
        status, page, _ = request(server, "GET", "/templates/script.default")
        assert status == 200
        assert "&lt;script&gt;alert" in page
        assert "<script>alert" not in page
    finally:
        stop(server, thread)
