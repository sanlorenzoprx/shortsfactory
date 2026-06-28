from __future__ import annotations

import json
from pathlib import Path

import pytest

from compliance_check import main as compliance_main
from content_factory.compliance import (
    ComplianceChecklistError,
    generate_compliance_checklist,
    mark_compliance_reviewed,
)
from content_factory.previews import generate_preview_cards
from content_factory.previews.preview_models import PLATFORM_ORDER, SAFETY_FLAGS


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def create_compliance_sources(
    export_root: Path,
    job_id: str = "approved-job",
    *,
    youtube_title: str = "Safe title",
    youtube_description: str = "Safe description",
    tiktok_caption: str = "Safe caption",
    instagram_caption: str = "Safe caption",
    hashtags: str = "#shorts\n#startup\n",
) -> tuple[Path, Path]:
    export_dir = export_root / "approved" / job_id
    export_dir.mkdir(parents=True)
    write_json(export_dir / "APPROVAL.json", {"job_id": job_id, "state": "approved"})
    write_json(
        export_dir / "EXPORT_MANIFEST.json",
        {
            "job_id": job_id,
            "publishing_status": "not_published",
            "live_publishing_enabled": False,
        },
    )
    write_json(export_dir / "receipt.json", {"job_id": job_id})
    (export_dir / "final.mp4").write_bytes(b"video")
    (export_dir / "thumbnail.jpg").write_bytes(b"thumbnail")

    kit = export_root / "upload_kits" / job_id
    write_json(
        kit / "UPLOAD_KIT_MANIFEST.json",
        {"job_id": job_id, "platforms": list(PLATFORM_ORDER), **SAFETY_FLAGS},
    )
    for platform in PLATFORM_ORDER:
        directory = kit / platform
        directory.mkdir(parents=True)
        write_json(
            directory / "platform_metadata.json",
            {
                "job_id": job_id,
                "platform": platform,
                "caption": "Metadata caption",
                **SAFETY_FLAGS,
            },
        )
        (directory / "upload_checklist.md").write_text(
            "- [ ] Human review\n- [ ] Manual upload",
            encoding="utf-8",
        )
        (directory / "hashtags.txt").write_text(hashtags, encoding="utf-8")
        if platform == "youtube_shorts":
            (directory / "title.txt").write_text(youtube_title, encoding="utf-8")
            (directory / "description.txt").write_text(
                youtube_description,
                encoding="utf-8",
            )
        elif platform == "tiktok":
            (directory / "caption.txt").write_text(tiktok_caption, encoding="utf-8")
        else:
            (directory / "caption.txt").write_text(instagram_caption, encoding="utf-8")
    generate_preview_cards(job_id, export_root)
    return export_dir, kit


def load_checklist_json(export_root: Path, job_id: str = "approved-job") -> dict:
    return json.loads(
        (export_root / "upload_kits" / job_id / "compliance" / "COMPLIANCE_CHECKLIST.json").read_text(
            encoding="utf-8"
        )
    )


def test_compliance_cli_help_works(capsys):
    with pytest.raises(SystemExit) as excinfo:
        compliance_main(["--help"])
    assert excinfo.value.code == 0
    assert "final local compliance checklist" in capsys.readouterr().out


def test_compliance_refuses_missing_approved_export(tmp_path: Path):
    export_root = tmp_path / "exports"
    with pytest.raises(ComplianceChecklistError, match="approved export bundle is missing"):
        generate_compliance_checklist("approved-job", export_root)


def test_compliance_refuses_missing_upload_kit(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root)
    kit_root = export_root / "upload_kits" / "approved-job"
    for path in sorted(kit_root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    kit_root.rmdir()
    with pytest.raises(ComplianceChecklistError, match="manual upload kit is missing"):
        generate_compliance_checklist("approved-job", export_root)


def test_compliance_refuses_missing_preview_manifest(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root)
    (export_root / "upload_kits" / "approved-job" / "previews" / "PREVIEW_MANIFEST.json").unlink()
    with pytest.raises(ComplianceChecklistError, match="preview manifest is missing"):
        generate_compliance_checklist("approved-job", export_root)


def test_compliance_refuses_unsafe_safety_flags(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root)
    manifest_path = export_root / "upload_kits" / "approved-job" / "UPLOAD_KIT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["live_publishing_enabled"] = True
    write_json(manifest_path, manifest)
    with pytest.raises(ComplianceChecklistError, match="safety validation"):
        generate_compliance_checklist("approved-job", export_root)


def test_compliance_writes_json_and_markdown_with_default_review_state(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root)
    result = generate_compliance_checklist("approved-job", export_root)
    checklist_path = result.compliance_dir / "COMPLIANCE_CHECKLIST.json"
    markdown_path = result.compliance_dir / "COMPLIANCE_CHECKLIST.md"
    assert checklist_path.is_file()
    assert markdown_path.is_file()
    checklist = load_checklist_json(export_root)
    assert checklist["status"] == "needs_human_review"
    assert checklist["ready_for_manual_upload"] is False
    required = {
        item["id"]: item["status"]
        for item in checklist["checks"]
        if item["severity"] == "required"
    }
    assert required["approved_export_exists"] == "pass"
    assert required["preview_manifest_exists"] == "pass"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Final Manual Upload Compliance Checklist" in markdown
    assert "Needs Human Review" in markdown
    assert "Manual upload only." in markdown


def test_compliance_detects_placeholder_and_risk_phrase_warnings(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(
        export_root,
        youtube_title="TODO guaranteed instant results <title>",
        youtube_description="Use {hook} now.",
    )
    checklist = generate_compliance_checklist("approved-job", export_root).checklist
    codes = {item["code"] for item in checklist["warnings"]}
    assert "youtube_title_banned_text" in codes
    assert "youtube_title_risky_phrase" in codes
    assert "youtube_description_template_placeholder" in codes
    assert any(item["status"] == "warn" for item in checklist["checks"])


def test_compliance_mark_reviewed_requires_machine_pass_and_keeps_safety_flags(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root)
    result = mark_compliance_reviewed("approved-job", export_root)
    checklist = result.checklist
    assert checklist["status"] == "ready_for_manual_upload"
    assert checklist["ready_for_manual_upload"] is True
    assert checklist["review_method"] == "local_cli"
    assert checklist["safety"] == SAFETY_FLAGS
    assert all(item["checked"] is True for item in checklist["human_review_items"])
    export_manifest = json.loads(
        (export_root / "approved" / "approved-job" / "EXPORT_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert export_manifest["publishing_status"] == "not_published"
    assert export_manifest["live_publishing_enabled"] is False


def test_compliance_mark_reviewed_refuses_failed_machine_checks(tmp_path: Path):
    export_root = tmp_path / "exports"
    create_compliance_sources(export_root, youtube_title="")
    with pytest.raises(ComplianceChecklistError, match="required machine checks failed"):
        mark_compliance_reviewed("approved-job", export_root)
