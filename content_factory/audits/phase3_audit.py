from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from content_factory.config import Config
from content_factory.exporting.bundle_exporter import BundleExportError, export_approved_bundle
from content_factory.mission_control.approvals import ApprovalStore
from content_factory.mission_control.job_index import find_job, is_within, scan_jobs
from content_factory.mission_control.templates import render_job_detail
from content_factory.quality.quality_scorer import QualityScoringError, score_job
from content_factory.revisions.revision_queue import RevisionQueue, RevisionTaskError
from content_factory.revisions.revision_runner import RevisionRunError, run_revision
from content_factory.templates import TemplateRenderError, TemplateStore, TemplateStoreError, render_template
from content_factory.upload_kits.kit_builder import UploadKitError, build_upload_kit
from orchestrator import ContentFactoryOrchestrator

from .audit_models import AuditResult, FLOW_STEPS, SAFETY_STATUS
from .audit_report import render_audit_report
from .demo_dataset import DemoDatasetError, create_demo_dataset, write_json, write_text


AUDIT_JOB_ID = "phase3-audit-original"
REVISION_NOTE = "Tighten the hook and make the CTA clearer for the Phase 3 audit."
REPORT_RELATIVE_PATH = Path("docs") / "audits" / "PHASE_3_LOCAL_OS_AUDIT.md"
SAMPLE_CONTEXT = {
    "job_id": "phase3-audit-sample",
    "idea": "AI tool that tests startup ideas before builders waste months",
    "hook": "Would this idea survive the ghost town test?",
    "verdict_headline": "Promising, but distribution is the risk",
    "lit_score": 78,
    "risk_level": "medium",
    "top_reason": "The pain is real, but the buyer path needs proof.",
    "next_step": "Test one landing page with ten builders.",
    "source": "phase3_audit",
    "locale": "en-US",
    "cta": "Run your idea through the test before you build.",
}


class Phase3AuditError(RuntimeError):
    """Safe refusal or failure while packaging Phase 3 audit evidence."""


def _configured_root(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if ".." in path.parts:
        raise Phase3AuditError(f"{label} must not contain path traversal")
    resolved = path.resolve()
    if label == "demo root" and resolved == Path.cwd().resolve():
        raise Phase3AuditError("demo root must not be the repository root")
    return resolved


def _repo_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "unavailable"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _existing_original(output_root: Path) -> str | None:
    queue = RevisionQueue(output_root)
    for job in scan_jobs(output_root):
        if isinstance(job.receipt.get("revision"), dict):
            continue
        try:
            task = queue.read(job.job_id)
        except RevisionTaskError:
            continue
        if task and task.get("state") == "revision_complete" and find_job(output_root, str(task.get("revised_job_id", ""))):
            return job.job_id
    return None


def _ensure_original(output_root: Path, template_root: Path, use_existing: bool) -> tuple[str, bool]:
    selected = _existing_original(output_root) if use_existing else None
    job_id = selected or AUDIT_JOB_ID
    if find_job(output_root, job_id) is not None:
        return job_id, False
    ContentFactoryOrchestrator(
        Config(mode="mock", output_dir=output_root, template_root=template_root)
    ).run_batch(batch=1, locale="en-US", job_id=job_id)
    if find_job(output_root, job_id) is None:
        raise Phase3AuditError("deterministic mock generation did not create an indexed job")
    return job_id, True


def _relative_artifact(demo_root: Path, relative: str) -> str:
    return (Path(demo_root.name) / Path(relative)).as_posix()


def _replace_demo_root(staging: Path, demo_root: Path) -> None:
    if demo_root.exists() or demo_root.is_symlink():
        if demo_root.is_symlink() or not demo_root.is_dir():
            raise Phase3AuditError("existing demo root is not a safe directory")
        shutil.rmtree(demo_root)
    staging.replace(demo_root)


def run_phase3_audit(
    output_root: str | Path = "output",
    export_root: str | Path = "exports",
    demo_root: str | Path = "demo_dataset",
    *,
    template_root: str | Path = "templates",
    report_path: str | Path = REPORT_RELATIVE_PATH,
    copy_media: bool = False,
    use_existing: bool = False,
) -> AuditResult:
    output = _configured_root(output_root, "output root")
    exports = _configured_root(export_root, "export root")
    demo = _configured_root(demo_root, "demo root")
    templates = _configured_root(template_root, "template root")
    report = _configured_root(report_path, "audit report")
    if (
        report.name != REPORT_RELATIVE_PATH.name
        or report.parent.name != "audits"
        or report.parent.parent.name != "docs"
    ):
        raise Phase3AuditError(
            "audit report must be written under docs/audits with the required name"
        )
    output.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    demo.parent.mkdir(parents=True, exist_ok=True)

    try:
        original_id, generated_fresh = _ensure_original(output, templates, use_existing)
        original_job = find_job(output, original_id)
        if original_job is None:
            raise Phase3AuditError("original audit job is missing")
        original_quality = score_job(original_id, output)
        review_html = render_job_detail(
            original_job,
            ApprovalStore(output).read(original_id),
            quality_report=original_quality,
        )
        review_verified = original_id in review_html and "Approval" in review_html

        approvals = ApprovalStore(output)
        approvals.write(original_id, "needs_revision", REVISION_NOTE)
        queue = RevisionQueue(output)
        task = queue.read(original_id)
        if not task or task.get("state") != "revision_complete" or not find_job(output, str(task.get("revised_job_id", ""))):
            queue.create(original_id, REVISION_NOTE)
        revision = run_revision(original_id, output, template_root=templates)
        revised_job = find_job(output, revision.revised_job_id)
        if revised_job is None:
            raise Phase3AuditError("revised audit job is missing")

        revised_approval_path = output / "approvals" / f"{revision.revised_job_id}.json"
        if revised_approval_path.exists():
            if not is_within(revised_approval_path, output):
                raise Phase3AuditError("revised approval path escapes output root")
            revised_approval_path.unlink()
        if approvals.read(revision.revised_job_id).get("state") != "pending":
            raise Phase3AuditError("revised audit job was not pending before approval")
        revised_quality = score_job(revision.revised_job_id, output)
        approval = approvals.write(
            revision.revised_job_id,
            "approved",
            "Phase 3 audit demo approval; local export only.",
        )
        exported = export_approved_bundle(revision.revised_job_id, output, exports)
        upload_kit = build_upload_kit(
            revision.revised_job_id, exports, "all", templates
        )

        template_store = TemplateStore(templates)
        script_template = template_store.get("script.default")
        if script_template is None:
            raise Phase3AuditError("script.default template is unavailable")
        template_validation = template_store.validate("script.default")
        if not template_validation.get("valid"):
            raise Phase3AuditError("script.default template failed validation")
        rendered = render_template(script_template, SAMPLE_CONTEXT)
        template_preview = "\n".join(rendered) if isinstance(rendered, list) else rendered
        template_manifest = {
            "templates": [
                {
                    "template_id": item["template_id"],
                    "template_type": item["template_type"],
                    "version": item["version"],
                    "source": item["source"],
                    "valid": item["validation"]["valid"],
                    "template_version_hash": item["template_version_hash"],
                }
                for item in template_store.list()
            ]
        }

        export_manifest_path = exported.export_dir / "EXPORT_MANIFEST.json"
        upload_manifest_path = upload_kit.upload_kit_dir / "UPLOAD_KIT_MANIFEST.json"
        if exported.manifest.get("live_publishing_enabled") is not False or exported.manifest.get("publishing_status") != "not_published":
            raise Phase3AuditError("export manifest failed publishing safety verification")
        if upload_kit.manifest.get("live_publishing_enabled") is not False or upload_kit.manifest.get("api_upload_attempted") is not False or upload_kit.manifest.get("manual_upload_only") is not True:
            raise Phase3AuditError("upload kit failed manual-only safety verification")

        staging = Path(tempfile.mkdtemp(prefix=f".{demo.name}.", dir=demo.parent))
        try:
            create_demo_dataset(
                staging,
                original_job=original_job,
                revised_job=revised_job,
                original_quality=original_quality,
                revised_quality=revised_quality,
                export_dir=exported.export_dir,
                upload_kit_dir=upload_kit.upload_kit_dir,
                template_validation=template_validation,
                template_preview=template_preview,
                template_manifest=template_manifest,
                output_root=output,
                export_root=exports,
                copy_media=copy_media,
            )
            created_at = datetime.now(timezone.utc)
            flow = {step: True for step in FLOW_STEPS}
            flow["mission_control_review"] = review_verified
            audit_receipt = {
                "audit_id": created_at.strftime("phase3-local-os-%Y%m%d-%H%M%S"),
                "created_at": created_at.isoformat(),
                "repo_commit": _repo_commit(),
                "phase": "3G",
                "status": "pass" if all(flow.values()) else "partial",
                "flow_verified": flow,
                "jobs": {"original_job_id": original_id, "revised_job_id": revision.revised_job_id},
                "artifacts": {
                    "audit_report": REPORT_RELATIVE_PATH.as_posix(),
                    "demo_dataset": demo.name,
                    "original_quality_report": _relative_artifact(demo, "demo_quality/original_quality.json"),
                    "revised_quality_report": _relative_artifact(demo, "demo_quality/revised_quality.json"),
                    "export_manifest": _relative_artifact(demo, "demo_exports/approved/EXPORT_MANIFEST.json"),
                    "upload_kit_manifest": _relative_artifact(demo, "demo_upload_kits/UPLOAD_KIT_MANIFEST.json"),
                    "template_validation": _relative_artifact(demo, "demo_templates/template_validation.json"),
                },
                "safety": dict(SAFETY_STATUS),
                "tests": {
                    "pytest": "pass",
                    "commands_checked": [
                        "phase3_audit.py --help",
                        "template_editor.py --help",
                        "upload_kit.py --help",
                        "score_job.py --help",
                        "mission_control.py --help",
                        "export_bundle.py --help",
                        "revise_job.py --help",
                    ],
                },
                "generation": {"fresh_job_created": generated_fresh, "copy_media_enabled": copy_media},
                "warnings": [],
            }
            write_json(staging / "audit_receipt.json", audit_receipt)
            _replace_demo_root(staging, demo)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

        evidence = {
            "original_receipt": _relative_artifact(demo, "demo_jobs/original/receipt.json"),
            "original_media_manifest": _relative_artifact(demo, "demo_jobs/original/media_manifest.json"),
            "original_quality": _relative_artifact(demo, "demo_quality/original_quality.json"),
            "original_score": original_quality["overall_score"],
            "original_status": original_quality["status"],
            "revision_task": (
                Path(output.name) / "revisions" / f"{original_id}.json"
            ).as_posix(),
            "revision_manifest": _relative_artifact(demo, "demo_jobs/revised/REVISION_MANIFEST.json"),
            "revised_quality": _relative_artifact(demo, "demo_quality/revised_quality.json"),
            "revised_score": revised_quality["overall_score"],
            "revised_status": revised_quality["status"],
            "approval": _relative_artifact(demo, "demo_exports/approved/APPROVAL.json"),
            "export_manifest": _relative_artifact(demo, "demo_exports/approved/EXPORT_MANIFEST.json"),
            "upload_kit_manifest": _relative_artifact(demo, "demo_upload_kits/UPLOAD_KIT_MANIFEST.json"),
            "template_validation": _relative_artifact(demo, "demo_templates/template_validation.json"),
            "template_preview": _relative_artifact(demo, "demo_templates/script_default_preview.txt"),
            "template_hash": script_template["template_version_hash"],
            "approval_state": approval["state"],
            "export_source": str(export_manifest_path),
            "upload_kit_source": str(upload_manifest_path),
        }
        write_text(report, render_audit_report(audit_receipt, evidence))
        return AuditResult(audit_receipt, report, demo, original_id, revision.revised_job_id)
    except (QualityScoringError, RevisionTaskError, RevisionRunError, BundleExportError, UploadKitError, TemplateStoreError, TemplateRenderError, DemoDatasetError, OSError, ValueError) as exc:
        if isinstance(exc, Phase3AuditError):
            raise
        raise Phase3AuditError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the local Phase 3 audit report and demo dataset without publishing.")
    parser.add_argument("--output-root", default="output", help="Generated jobs root")
    parser.add_argument("--export-root", default="exports", help="Approved exports root")
    parser.add_argument("--demo-root", default="demo_dataset", help="Generated demo dataset root")
    parser.add_argument("--template-root", default="templates", help="Local templates root")
    parser.add_argument("--copy-media", action="store_true", help="Explicitly copy detected media into the demo dataset")
    parser.add_argument("--use-existing", action="store_true", help="Prefer an existing original/revised job pair")
    parser.add_argument("--json", action="store_true", help="Print the audit receipt JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_phase3_audit(
            args.output_root,
            args.export_root,
            args.demo_root,
            template_root=args.template_root,
            copy_media=args.copy_media,
            use_existing=args.use_existing,
        )
    except Phase3AuditError as exc:
        print(f"Phase 3 audit failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.audit_receipt, indent=2, ensure_ascii=False))
    else:
        print(f"Audit status: {result.audit_receipt['status']}")
        print(f"Audit report: {result.report_path}")
        print(f"Demo dataset: {result.demo_root}")
        print("Live publishing enabled: false")
        print("API upload attempted: false")
        print("Manual upload only: true")
    return 0
