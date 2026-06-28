import json
from pathlib import Path

import pytest

from content_factory.templates import TemplateStore, TemplateStoreError


def test_save_increments_version_and_writes_history(tmp_path: Path):
    store = TemplateStore(tmp_path / "templates")
    template = store.get("script.default")
    template["name"] = "Edited locally"
    saved = store.save("script.default", template)
    assert saved["version"] == 2
    assert store.get("script.default")["name"] == "Edited locally"
    assert len(store.history("script.default")) == 1


def test_restore_validates_and_creates_a_new_version(tmp_path: Path):
    store = TemplateStore(tmp_path)
    template = store.get("script.default")
    template["name"] = "Version two"
    store.save("script.default", template)
    history_id = store.history("script.default")[0]["history_id"]
    restored = store.restore("script.default", history_id)
    assert restored["version"] == 3
    assert restored["name"] == "Default LIT Script"
    assert len(store.history("script.default")) == 2


def test_restore_refuses_invalid_history(tmp_path: Path):
    store = TemplateStore(tmp_path)
    template = store.get("script.default")
    store.save("script.default", template)
    item = store.history("script.default")[0]
    Path(item["path"]).write_text(json.dumps({"template_id": "script.default"}), encoding="utf-8")
    with pytest.raises(TemplateStoreError, match="History revision is invalid"):
        store.restore("script.default", item["history_id"])


def test_locked_template_cannot_be_overwritten(tmp_path: Path):
    store = TemplateStore(tmp_path)
    template = store.get("quality_message.default")
    with pytest.raises(TemplateStoreError, match="locked"):
        store.save("quality_message.default", template)
