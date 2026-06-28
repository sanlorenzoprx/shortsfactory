import json
from pathlib import Path

import pytest

from content_factory.upload_kits.kit_builder import UploadKitError, build_upload_kit


def write_approved_export(
    export_root: Path,
    job_id: str = "kit-job",
    optional: bool = True,
) -> Path:
    export_dir = export_root / "approved" / job_id
    export_dir.mkdir(parents=True)
    manifest = {
        "job_id": job_id,
        "approval_state": "approved",
        "publishing_status": "not_published",
        "live_publishing_enabled": False,
    }
    approval = {"job_id": job_id, "state": "approved"}
    receipt = {
        "job_id": job_id,
        "idea": {"name": "Local Builder Test"},
        "verdict": {
            "verdict_headline": "Test this idea before you build",
            "top_reason": "The score is promising.",
        },
    }
    (export_dir / "EXPORT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    (export_dir / "APPROVAL.json").write_text(json.dumps(approval), encoding="utf-8")
    (export_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (export_dir / "final.mp4").write_bytes(b"approved-video")
    (export_dir / "script.txt").write_text(
        "Test this builder idea.\nScore: 82.\nTest it now before you build.\n",
        encoding="utf-8",
    )
    if optional:
        (export_dir / "thumbnail.jpg").write_bytes(b"jpeg")
        (export_dir / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nTest it\n", encoding="utf-8")
    return export_dir


def test_upload_kit_refuses_missing_export_bundle(tmp_path):
    with pytest.raises(UploadKitError, match="approved export bundle is missing"):
        build_upload_kit("missing-job", tmp_path / "exports", "all")


def test_upload_kit_refuses_non_approved_export(tmp_path):
    export_root = tmp_path / "exports"
    export_dir = write_approved_export(export_root)
    approval = json.loads((export_dir / "APPROVAL.json").read_text(encoding="utf-8"))
    approval["state"] = "pending"
    (export_dir / "APPROVAL.json").write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(UploadKitError, match="not approved"):
        build_upload_kit("kit-job", export_root, "all")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("live_publishing_enabled", True, "live_publishing_enabled: false"),
        ("publishing_status", None, "publishing_status: not_published"),
    ],
)
def test_upload_kit_refuses_unsafe_export_manifest(tmp_path, field, value, message):
    export_root = tmp_path / "exports"
    export_dir = write_approved_export(export_root)
    manifest = json.loads((export_dir / "EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    if value is None:
        manifest.pop(field)
    else:
        manifest[field] = value
    (export_dir / "EXPORT_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(UploadKitError, match=message):
        build_upload_kit("kit-job", export_root, "all")


@pytest.mark.parametrize("platform", ["youtube_shorts", "tiktok", "instagram_reels"])
def test_upload_kit_creates_each_platform_with_required_files(tmp_path, platform):
    export_root = tmp_path / "exports"
    source = write_approved_export(export_root)

    result = build_upload_kit("kit-job", export_root, platform)

    platform_dir = result.upload_kit_dir / platform
    assert platform_dir.is_dir()
    assert (platform_dir / "final.mp4").read_bytes() == (source / "final.mp4").read_bytes()
    assert (platform_dir / "platform_metadata.json").is_file()
    assert (platform_dir / "upload_checklist.md").is_file()
    assert (platform_dir / "hashtags.txt").is_file()
    if platform == "youtube_shorts":
        assert (platform_dir / "title.txt").is_file()
        assert (platform_dir / "description.txt").is_file()
    else:
        assert (platform_dir / "caption.txt").is_file()


def test_all_creates_all_platforms_and_copies_optional_assets(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root)

    result = build_upload_kit("kit-job", export_root, "all")

    assert result.manifest["platforms"] == ["youtube_shorts", "tiktok", "instagram_reels"]
    for platform in result.manifest["platforms"]:
        platform_dir = result.upload_kit_dir / platform
        assert (platform_dir / "final.mp4").is_file()
        assert (platform_dir / "thumbnail.jpg").is_file()
        assert (platform_dir / "captions.srt").is_file()


def test_missing_optional_assets_are_recorded_without_failure(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root, optional=False)

    result = build_upload_kit("kit-job", export_root, "all")

    for platform in result.manifest["platforms"]:
        assert result.manifest["missing_optional_files"][platform] == [
            "thumbnail.jpg",
            "captions.srt",
        ]


def test_unsupported_platform_and_path_traversal_are_rejected(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root)
    with pytest.raises(UploadKitError, match="unsupported platform"):
        build_upload_kit("kit-job", export_root, "facebook")
    with pytest.raises(UploadKitError, match="invalid job_id"):
        build_upload_kit("../escape", export_root, "all")


def test_rerun_replaces_platform_deterministically_without_duplicates(tmp_path):
    export_root = tmp_path / "exports"
    write_approved_export(export_root)
    first = build_upload_kit("kit-job", export_root, "all")
    first_manifest = (first.upload_kit_dir / "UPLOAD_KIT_MANIFEST.json").read_bytes()
    (first.upload_kit_dir / "tiktok" / "stale.txt").write_text("remove", encoding="utf-8")

    second = build_upload_kit("kit-job", export_root, "all")

    assert second.upload_kit_dir == first.upload_kit_dir
    assert not (second.upload_kit_dir / "tiktok" / "stale.txt").exists()
    assert (second.upload_kit_dir / "UPLOAD_KIT_MANIFEST.json").read_bytes() == first_manifest
    assert sorted(path.name for path in second.upload_kit_dir.iterdir()) == [
        "UPLOAD_KIT_MANIFEST.json",
        "instagram_reels",
        "tiktok",
        "youtube_shorts",
    ]
