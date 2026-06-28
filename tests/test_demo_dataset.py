from __future__ import annotations

import json
from pathlib import Path

from content_factory.audits.demo_dataset import create_demo_dataset
from content_factory.mission_control.job_index import JobRecord


def _job(root: Path, job_id: str, revised: bool = False) -> JobRecord:
    directory = root / "jobs" / job_id
    directory.mkdir(parents=True)
    artifacts = {}
    for name, data in {
        "receipt.json": json.dumps({"job_id": job_id}).encode(),
        "script.txt": b"Audit script",
        "captions.srt": b"Audit captions",
        "short.mp4": b"media",
    }.items():
        path = directory / name
        path.write_bytes(data)
        artifacts[name] = path.resolve()
    if revised:
        path = directory / "REVISION_MANIFEST.json"
        path.write_text(json.dumps({"requires_reapproval": True}), encoding="utf-8")
        artifacts[path.name] = path.resolve()
    return JobRecord(job_id, directory.resolve(), "now", "en-US", "mock", "mock", "complete", (), artifacts, {"job_id": job_id})


def _sources(tmp_path: Path):
    output = tmp_path / "output"
    exports = tmp_path / "exports"
    original = _job(output, "original")
    revised = _job(output, "revised", True)
    export_dir = exports / "approved" / "revised"
    export_dir.mkdir(parents=True)
    (export_dir / "EXPORT_MANIFEST.json").write_text("{}", encoding="utf-8")
    (export_dir / "APPROVAL.json").write_text("{}", encoding="utf-8")
    (export_dir / "final.mp4").write_bytes(b"export-media")
    kit = exports / "upload_kits" / "revised"
    kit.mkdir(parents=True)
    (kit / "UPLOAD_KIT_MANIFEST.json").write_text("{}", encoding="utf-8")
    for platform in ("youtube_shorts", "tiktok", "instagram_reels"):
        directory = kit / platform
        directory.mkdir()
        (directory / "platform_metadata.json").write_text("{}", encoding="utf-8")
        (directory / "upload_checklist.md").write_text("manual only", encoding="utf-8")
        (directory / "final.mp4").write_bytes(b"kit-media")
    return output.resolve(), exports.resolve(), original, revised, export_dir.resolve(), kit.resolve()


def _build(tmp_path: Path, destination: Path, copy_media: bool) -> None:
    output, exports, original, revised, export_dir, kit = _sources(tmp_path)
    create_demo_dataset(
        destination,
        original_job=original,
        revised_job=revised,
        original_quality={"status": "pass"},
        revised_quality={"status": "pass"},
        export_dir=export_dir,
        upload_kit_dir=kit,
        template_validation={"valid": True},
        template_preview="preview",
        template_manifest={"templates": []},
        output_root=output,
        export_root=exports,
        copy_media=copy_media,
    )


def test_demo_dataset_omits_large_media_by_default(tmp_path: Path):
    destination = tmp_path / "demo"
    _build(tmp_path, destination, False)
    assert not (destination / "demo_jobs" / "original" / "short.mp4").exists()
    assert not (destination / "demo_exports" / "approved" / "final.mp4").exists()
    assert not (destination / "demo_upload_kits" / "tiktok" / "final.mp4").exists()
    manifest = json.loads((destination / "demo_exports" / "approved" / "export_file_manifest.json").read_text(encoding="utf-8"))
    assert next(item for item in manifest["files"] if item["name"] == "final.mp4")["copied"] is False


def test_demo_dataset_copies_media_only_when_explicit(tmp_path: Path):
    destination = tmp_path / "demo-with-media"
    _build(tmp_path, destination, True)
    assert (destination / "demo_jobs" / "original" / "short.mp4").read_bytes() == b"media"
    assert (destination / "demo_exports" / "approved" / "final.mp4").read_bytes() == b"export-media"
    assert (destination / "demo_upload_kits" / "tiktok" / "final.mp4").read_bytes() == b"kit-media"
