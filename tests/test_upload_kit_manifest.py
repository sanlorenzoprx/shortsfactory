import json
from pathlib import Path

import pytest

from content_factory.upload_kits.kit_builder import build_upload_kit
from content_factory.upload_kits.manifest import UploadKitManifestError, read_upload_kit_manifest


def write_approved_export(export_root: Path) -> None:
    export_dir = export_root / "approved" / "kit-job"
    export_dir.mkdir(parents=True)
    (export_dir / "EXPORT_MANIFEST.json").write_text(
        json.dumps(
            {
                "job_id": "kit-job",
                "publishing_status": "not_published",
                "live_publishing_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    (export_dir / "APPROVAL.json").write_text(
        json.dumps({"job_id": "kit-job", "state": "approved"}), encoding="utf-8"
    )
    (export_dir / "receipt.json").write_text(
        json.dumps({"job_id": "kit-job", "verdict": {"verdict_headline": "Test it"}}),
        encoding="utf-8",
    )
    (export_dir / "final.mp4").write_bytes(b"video")


def test_upload_kit_manifest_and_platform_metadata_have_all_safety_flags(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root)

    result = build_upload_kit("kit-job", export_root, "all")
    manifest = read_upload_kit_manifest(export_root, "kit-job")

    for value in (manifest, *[
        json.loads((result.upload_kit_dir / platform / "platform_metadata.json").read_text(encoding="utf-8"))
        for platform in manifest["platforms"]
    ]):
        assert value["manual_upload_only"] is True
        assert value["publishing_status"] == "not_published"
        assert value["live_publishing_enabled"] is False
        assert value["api_upload_attempted"] is False
        assert value["requires_human_upload"] is True
    assert (result.upload_kit_dir / "UPLOAD_KIT_MANIFEST.json").is_file()


def test_manifest_reader_rejects_unsafe_existing_manifest(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root)
    result = build_upload_kit("kit-job", export_root, "youtube_shorts")
    path = result.upload_kit_dir / "UPLOAD_KIT_MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["live_publishing_enabled"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UploadKitManifestError, match="safety validation"):
        read_upload_kit_manifest(export_root, "kit-job")
