from pathlib import Path

import pytest

from content_factory.agents.script_writer import ScriptWriter
from content_factory.agents.caption_agent import CaptionAgent
from content_factory.agents.thumbnail_agent import ThumbnailAgent
from content_factory.revisions.revision_runner import revise_script
from content_factory.schemas import Idea, LitVerdict, ShortScript
from content_factory.config import Config
from content_factory.upload_kits.metadata_formatter import format_platform_copy
from content_factory.upload_kits.platform_profiles import PLATFORM_PROFILES
from content_factory.templates import TemplateRenderError, TemplateStore, render_template
from content_factory.templates.default_templates import builtin_templates
from orchestrator import ContentFactoryOrchestrator
import json


def context():
    return {"hook": "Hook", "lit_score": 80, "risk_level": "medium", "top_reason": "Reason", "verdict_headline": "Promising", "cta": "Test it"}


def test_rendering_is_deterministic_and_does_not_execute_text(tmp_path: Path):
    template = builtin_templates()["script.default"]
    template["content"][0] = "literal __import__('os').system('bad') {hook}"
    first = render_template(template, context())
    assert first == render_template(template, context())
    assert first[0].startswith("literal __import__")
    assert not list(tmp_path.iterdir())


def test_rendering_fails_when_required_context_is_missing():
    template = builtin_templates()["script.default"]
    with pytest.raises(TemplateRenderError, match="lit_score"):
        render_template(template, {"hook": "only one value"})


def verdict() -> LitVerdict:
    return LitVerdict(Idea("Template idea", "Description"), "Promising", 82, "medium", "Clear demand", "Test it", "mock")


def test_script_writer_uses_local_template_and_falls_back_when_invalid(tmp_path: Path):
    root = tmp_path / "templates"
    store = TemplateStore(root)
    template = store.get("script.default")
    template["content"][0] = "CUSTOM {hook}"
    saved = store.save("script.default", template)
    writer = ScriptWriter(root)
    script = writer.generate_script(verdict())
    assert script.hook.startswith("CUSTOM I ran")
    assert writer.last_template_usage["template_version_hash"] == saved["template_version_hash"]

    saved["content"].append("{unknown}")
    (root / "script" / "default.json").write_text(__import__("json").dumps(saved), encoding="utf-8")
    fallback = writer.generate_script(verdict())
    assert fallback.hook.startswith("I ran this business idea")
    assert writer.last_template_usage is None
    assert "fallback used" in writer.last_template_warning


def test_revision_runner_uses_local_revision_template(tmp_path: Path):
    store = TemplateStore(tmp_path)
    template = store.get("revision.default")
    template["content"] = "Human request: {revision_note}"
    store.save("revision.default", template)
    original = ShortScript("Hook", ["Body"], "Verdict", "CTA")
    revised = revise_script(original, "Use proof", "Idea", "en-US", tmp_path)
    assert revised.body_lines[-1] == "Human request: Use proof"


def test_upload_metadata_uses_local_platform_template(tmp_path: Path):
    store = TemplateStore(tmp_path)
    template = store.get("publisher_metadata.tiktok")
    template["content"] = "CUSTOM {caption}"
    store.save("publisher_metadata.tiktok", template)
    copy = format_platform_copy(
        PLATFORM_PROFILES["tiktok"],
        {"verdict": {"verdict_headline": "Promising"}},
        "Test this idea.\nTry it now.",
        {},
        tmp_path,
    )
    assert copy["caption"].startswith("CUSTOM Promising")
    assert copy["template"]["template_id"] == "publisher_metadata.tiktok"


def test_orchestrator_receipt_records_script_template_usage(tmp_path: Path, monkeypatch):
    root = tmp_path / "templates"
    store = TemplateStore(root)
    template = store.get("script.default")
    template["content"][0] = "LOCAL {hook}"
    saved = store.save("script.default", template)
    orchestrator = ContentFactoryOrchestrator(Config(mode="mock", output_dir=tmp_path / "output", template_root=root))

    def fake_video(_script, _verdict, job_dir, **_kwargs):
        path = job_dir / "short.mp4"
        path.write_bytes(b"video")
        return path

    monkeypatch.setattr(orchestrator.video, "create_short", fake_video)
    receipt_path = orchestrator.run_batch()[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["templates"]["script"] == {
        "template_id": "script.default",
        "template_version_hash": saved["template_version_hash"],
        "source": "local_template",
    }
    assert receipt["templates"]["caption"]["template_id"] == "caption.default"
    assert receipt["templates"]["thumbnail"]["template_id"] == "thumbnail.default"


def test_caption_and_thumbnail_agents_use_local_text_templates(tmp_path: Path):
    root = tmp_path / "templates"
    store = TemplateStore(root)
    caption_template = store.get("caption.default")
    caption_template["content"] = "CUSTOM {caption}"
    store.save("caption.default", caption_template)
    thumbnail_template = store.get("thumbnail.default")
    thumbnail_template["content"][0] = "CUSTOM {title}"
    store.save("thumbnail.default", thumbnail_template)
    script = ShortScript("Hook", ["Body"], "Verdict", "CTA")
    caption_agent = CaptionAgent(root)
    caption_path = caption_agent.generate_captions(script, tmp_path / "captions.srt")
    assert "CUSTOM Hook" in caption_path.read_text(encoding="utf-8")
    assert caption_agent.last_template_usage["template_id"] == "caption.default"
    thumbnail_agent = ThumbnailAgent(root)
    thumbnail_path = thumbnail_agent.create_thumbnail(verdict(), tmp_path / "thumbnail.jpg")
    assert thumbnail_path.is_file()
    assert thumbnail_agent.last_template_usage["template_id"] == "thumbnail.default"
