from pathlib import Path

import pytest

from content_factory.templates.registry import TemplateRegistry


def test_registry_lists_all_required_builtin_template_families(tmp_path: Path):
    templates = TemplateRegistry(tmp_path / "templates").list()
    ids = {item["template_id"] for item in templates}
    assert "script.default" in ids
    assert "caption.default" in ids
    assert "thumbnail.default" in ids
    assert "publisher_metadata.youtube_shorts" in ids
    assert "upload_checklist.tiktok" in ids
    assert "revision.default" in ids
    assert all(item["validation"]["valid"] for item in templates)


@pytest.mark.parametrize("template_id", ["../escape", "script/escape", "script..", "script.default/../../x"])
def test_registry_rejects_path_traversal(tmp_path: Path, template_id: str):
    with pytest.raises(ValueError, match="invalid template_id"):
        TemplateRegistry(tmp_path).local_path(template_id)
