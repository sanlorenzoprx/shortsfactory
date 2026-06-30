from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from content_factory.autopilot.youtube_metadata import (
    CANONICAL_TAGS,
    SCHEMA_VERSION,
    YouTubeMetadataError,
    YouTubeMetadataHardener,
    YouTubeUploadMetadataV1,
    main,
)


NOW = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    output = tmp_path / "output"
    job_id = "ap-metadata-job"
    job_dir = output / "jobs" / job_id
    video = job_dir / "short.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"generated-video")
    receipt = _write(job_dir / "receipt.json", {
        "job_id": job_id,
        "outputs": {"short_mp4": str(video)},
    })
    metadata = _write(job_dir / "publish" / "youtube_shorts" / "metadata.json", {
        "status": "dry_run_ready",
        "live_publish_enabled": False,
        "platform": "youtube_shorts",
        "source_job_id": job_id,
        "locale": "en-US",
        "title": "Build a tiny test now",
        "description": "Validate one painful use case before building.",
        "caption": "Test demand before building. #Shorts",
        "hashtags": ["#BusinessIdeas", "Startup", "#Shorts"],
        "tags": ["#Custom Tag", " startup validation "],
        "video": "../../short.mp4",
        "thumbnail": "../../thumbnail.jpg",
        "captions": "captions.srt",
    })
    plan = _write(job_dir / "publish" / "publisher_plan.json", {
        "status": "dry_run_ready",
        "live_publish_enabled": False,
        "requires_human_approval": True,
        "source_job_id": job_id,
        "platforms": {"youtube_shorts": "youtube_shorts/metadata.json"},
    })
    return {
        "output": output,
        "job_id": job_id,
        "job_dir": job_dir,
        "video": video,
        "receipt": receipt,
        "metadata": metadata,
        "plan": plan,
    }


def _hardener(files: dict[str, Path | str]) -> YouTubeMetadataHardener:
    return YouTubeMetadataHardener(output_root=files["output"], now=lambda: NOW)


def test_hardening_builds_versioned_upload_ready_metadata(tmp_path):
    files = _fixture(tmp_path)
    result = _hardener(files).harden(job_id=str(files["job_id"]))
    metadata = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
    assert metadata["schema_version"] == SCHEMA_VERSION
    assert metadata["privacy_status"] == "private"
    assert metadata["made_for_kids"] is False
    assert metadata["category_id"] == "22"
    assert metadata["hashtags"] == ["#BusinessIdeas", "#Startup", "#Shorts"]
    assert "Custom Tag" in metadata["tags"]
    assert all(not tag.startswith("#") for tag in metadata["tags"])
    assert all(tag in metadata["tags"] for tag in CANONICAL_TAGS)
    assert metadata["title"] == "Build a tiny test now"
    assert metadata["caption"] == "Test demand before building. #Shorts"
    assert result.supervised_upload_command.startswith("python youtube_supervised_upload.py")
    assert str(files["video"]) in result.supervised_upload_command


@pytest.mark.parametrize("url", [
    "ftp://ghosttown.test",
    "https://user:password@ghosttown.test",
    "https://accounts.google.com/o/oauth2/auth",
    "https://ghosttown.test/?access_token=secret",
])
def test_invalid_or_auth_website_url_is_rejected(tmp_path, url):
    files = _fixture(tmp_path)
    before = Path(files["metadata"]).read_bytes()
    with pytest.raises(YouTubeMetadataError, match="website_url"):
        _hardener(files).harden(job_id=str(files["job_id"]), website_url=url)
    assert Path(files["metadata"]).read_bytes() == before


def test_safe_website_and_cta_are_added_only_to_description_content(tmp_path):
    files = _fixture(tmp_path)
    website = "https://ghosttown.example/test"
    cta = "Follow Ghost Town Test for more business idea tests."
    _hardener(files).harden(
        job_id=str(files["job_id"]),
        website_url=website,
        cta_text=cta,
    )
    metadata = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
    assert website in metadata["description"]
    assert cta in metadata["description"]
    assert website not in metadata["title"]
    assert website not in metadata["caption"]
    assert all(website not in tag for tag in metadata["tags"])
    assert metadata["website_url"] == website
    assert metadata["cta_text"] == cta


def test_auth_url_in_cta_is_rejected(tmp_path):
    files = _fixture(tmp_path)
    with pytest.raises(YouTubeMetadataError, match="authentication URLs"):
        _hardener(files).harden(
            job_id=str(files["job_id"]),
            cta_text="Continue at https://accounts.google.com/o/oauth2/auth",
        )


def test_publish_at_requires_private_privacy(tmp_path):
    files = _fixture(tmp_path)
    metadata = json.loads(Path(files["metadata"]).read_text(encoding="utf-8"))
    metadata["publish_at"] = "2026-07-01T18:00:00Z"
    _write(Path(files["metadata"]), metadata)
    with pytest.raises(YouTubeMetadataError, match="only when privacy_status is private"):
        _hardener(files).harden(
            job_id=str(files["job_id"]),
            privacy_status="public",
        )


def test_hardening_repairs_bom_and_writes_hash_receipt_without_bom(tmp_path):
    files = _fixture(tmp_path)
    metadata_path = Path(files["metadata"])
    previous = b"\xef\xbb\xbf" + metadata_path.read_bytes()
    metadata_path.write_bytes(previous)
    result = _hardener(files).harden(job_id=str(files["job_id"]))
    hardened = metadata_path.read_bytes()
    assert not hardened.startswith(b"\xef\xbb\xbf")
    receipt_bytes = Path(result.receipt_path).read_bytes()
    assert not receipt_bytes.startswith(b"\xef\xbb\xbf")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    assert receipt["previous_metadata_hash"] == hashlib.sha256(previous).hexdigest()
    assert receipt["new_metadata_hash"] == hashlib.sha256(hardened).hexdigest()
    assert receipt["utf8_without_bom"] is True
    assert receipt["previous_metadata_had_bom"] is True
    assert receipt["website_url_included"] is False
    assert receipt["cta_included"] is False
    assert receipt["secrets_recorded"] is False


def test_metadata_model_rejects_non_private_scheduled_upload():
    value = {
        "schema_version": SCHEMA_VERSION,
        "platform": "youtube_shorts",
        "source_job_id": "job",
        "title": "Title",
        "description": "Description",
        "caption": "Caption",
        "hashtags": ["#Shorts"],
        "tags": ["business ideas"],
        "category_id": "22",
        "privacy_status": "public",
        "made_for_kids": False,
        "video": "../../short.mp4",
        "publish_at": "2026-07-01T18:00:00Z",
        "thumbnail": None,
        "captions": None,
        "website_url": None,
        "cta_text": None,
        "source_receipt_references": {"generation_content_receipt": "receipt.json"},
        "generated_at": NOW.isoformat(),
    }
    with pytest.raises(YouTubeMetadataError, match="only when privacy_status is private"):
        YouTubeUploadMetadataV1.from_dict(value)


def test_versioned_contract_rejects_tags_with_hash_prefix():
    value = {
        "schema_version": SCHEMA_VERSION,
        "platform": "youtube_shorts",
        "source_job_id": "job",
        "title": "Title",
        "description": "Description",
        "caption": "Caption",
        "hashtags": ["#Shorts"],
        "tags": ["#not-clean"],
        "category_id": "22",
        "privacy_status": "private",
        "made_for_kids": False,
        "video": "../../short.mp4",
        "publish_at": None,
        "thumbnail": None,
        "captions": None,
        "website_url": None,
        "cta_text": None,
        "source_receipt_references": {"generation_content_receipt": "receipt.json"},
        "generated_at": NOW.isoformat(),
    }
    with pytest.raises(YouTubeMetadataError, match="without a leading #"):
        YouTubeUploadMetadataV1.from_dict(value)


def test_cli_accepts_powershell_empty_website_value_and_prints_next_command(tmp_path, capsys):
    files = _fixture(tmp_path)
    result = main([
        "harden",
        "--job-id", str(files["job_id"]),
        "--output-root", str(files["output"]),
        "--website-url",
        "--cta-text", "Follow Ghost Town Test for more business idea tests.",
    ])
    output = capsys.readouterr().out
    assert result == 0
    assert "Next supervised upload command:" in output
    assert "python youtube_supervised_upload.py" in output
