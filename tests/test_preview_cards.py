from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_factory.previews import PreviewCardError, generate_preview_cards
from content_factory.previews.preview_models import PLATFORM_ORDER, SAFETY_FLAGS


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def create_preview_sources(export_root: Path, job_id: str = "approved-job") -> tuple[Path, Path]:
    export_dir = export_root / "approved" / job_id
    export_dir.mkdir(parents=True)
    write_json(export_dir / "APPROVAL.json", {"job_id": job_id, "state": "approved"})
    write_json(export_dir / "EXPORT_MANIFEST.json", {"job_id": job_id, "publishing_status": "not_published", "live_publishing_enabled": False})
    write_json(export_dir / "receipt.json", {"job_id": job_id})
    (export_dir / "final.mp4").write_bytes(b"video")
    (export_dir / "thumbnail.jpg").write_bytes(b"thumbnail")

    kit = export_root / "upload_kits" / job_id
    manifest = {"job_id": job_id, "platforms": list(PLATFORM_ORDER), **SAFETY_FLAGS}
    write_json(kit / "UPLOAD_KIT_MANIFEST.json", manifest)
    for platform in PLATFORM_ORDER:
        directory = kit / platform
        directory.mkdir(parents=True)
        write_json(directory / "platform_metadata.json", {"job_id": job_id, "platform": platform, "caption": "Metadata caption", **SAFETY_FLAGS})
        (directory / "upload_checklist.md").write_text("- [ ] Human review\n- [ ] Manual upload", encoding="utf-8")
        (directory / "hashtags.txt").write_text("#shorts\n#startup\n", encoding="utf-8")
        if platform == "youtube_shorts":
            (directory / "title.txt").write_text("Safe title", encoding="utf-8")
            (directory / "description.txt").write_text("Safe description", encoding="utf-8")
        else:
            (directory / "caption.txt").write_text("Safe caption", encoding="utf-8")
    return export_dir, kit


def test_preview_generation_requires_manual_upload_kit(tmp_path: Path):
    export_root = tmp_path / "exports"
    export_dir, kit = create_preview_sources(export_root)
    for path in sorted(kit.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    kit.rmdir()
    with pytest.raises(PreviewCardError, match="manual upload kit is missing"):
        generate_preview_cards("approved-job", export_root)


def test_preview_generation_requires_approved_export(tmp_path: Path):
    export_root = tmp_path / "exports"
    export_dir, _ = create_preview_sources(export_root)
    (export_dir / "APPROVAL.json").write_text(json.dumps({"job_id": "approved-job", "state": "pending"}), encoding="utf-8")
    with pytest.raises(PreviewCardError, match="not approved"):
        generate_preview_cards("approved-job", export_root)


def test_preview_generation_refuses_unsafe_upload_flags(tmp_path: Path):
    export_root = tmp_path / "exports"
    _, kit = create_preview_sources(export_root)
    manifest = json.loads((kit / "UPLOAD_KIT_MANIFEST.json").read_text(encoding="utf-8"))
    manifest["live_publishing_enabled"] = True
    write_json(kit / "UPLOAD_KIT_MANIFEST.json", manifest)
    with pytest.raises(PreviewCardError, match="safety validation"):
        generate_preview_cards("approved-job", export_root)


def test_preview_generation_writes_manifest_html_and_text(tmp_path: Path):
    export_root = tmp_path / "exports"
    _, kit = create_preview_sources(export_root)
    result = generate_preview_cards("approved-job", export_root)
    expected = {"PREVIEW_MANIFEST.json"}
    for platform in PLATFORM_ORDER:
        expected.update({f"{platform}_preview.html", f"{platform}_preview.txt"})
    assert {path.name for path in result.preview_dir.iterdir()} == expected
    manifest = json.loads((result.preview_dir / "PREVIEW_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ready_for_manual_review"
    assert manifest["safety"] == SAFETY_FLAGS
    assert set(manifest["platforms"]) == set(PLATFORM_ORDER)
    assert result.preview_dir == kit.resolve() / "previews"
