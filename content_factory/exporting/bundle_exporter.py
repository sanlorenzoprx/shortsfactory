from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from content_factory.mission_control.approvals import validate_job_id
from content_factory.mission_control.job_index import JobRecord, find_job, is_within

from .manifest import build_export_manifest, export_directory, write_export_manifest


VIDEO_PRIORITY = (
    "final.mp4",
    "short_with_music.mp4",
    "short_with_voice.mp4",
    "short.mp4",
)

SUPPORTING_ARTIFACTS = (
    "thumbnail.jpg",
    "captions.srt",
    "script.txt",
    "publisher_package.json",
    "app_recording.mp4",
    "app_recording_final.png",
    "lit_api_response.json",
)


class BundleExportError(RuntimeError):
    """A safe, user-facing refusal to create an export bundle."""


@dataclass(frozen=True)
class ExportResult:
    job_id: str
    export_dir: Path
    manifest: dict[str, Any]


def _approval_snapshot(output_root: Path, job_id: str) -> bytes:
    approval_path = output_root / "approvals" / f"{validate_job_id(job_id)}.json"
    if not is_within(approval_path, output_root) or not approval_path.is_file():
        raise BundleExportError(f"job {job_id} is not approved: approval record is missing")
    try:
        raw = approval_path.read_bytes()
        approval = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleExportError(f"job {job_id} is not approved: approval record is invalid") from exc
    if not isinstance(approval, dict) or approval.get("job_id") != job_id:
        raise BundleExportError(f"job {job_id} is not approved: approval record does not match job")
    if approval.get("state") != "approved":
        state = approval.get("state", "unknown")
        raise BundleExportError(f"job {job_id} is not approved (current state: {state})")
    return raw


def _preferred_video(job: JobRecord) -> Path:
    for artifact_name in VIDEO_PRIORITY:
        if artifact_name in job.artifacts:
            return job.artifacts[artifact_name]
    raise BundleExportError(f"job {job.job_id} has no exportable MP4 video")


def _copy(source: Path, destination: Path, source_root: Path) -> None:
    if not source.is_file() or not is_within(source, source_root):
        raise BundleExportError(f"artifact is unavailable or outside output root: {source.name}")
    shutil.copy2(source, destination)


def export_approved_bundle(
    job_id: str,
    output_root: str | Path = "output",
    export_root: str | Path = "exports",
) -> ExportResult:
    """Create or deterministically replace one approved local export bundle."""
    try:
        safe_id = validate_job_id(job_id)
    except ValueError as exc:
        raise BundleExportError("invalid job_id") from exc
    source_root = Path(output_root).expanduser().resolve()
    destination_root = Path(export_root).expanduser().resolve()
    job = find_job(source_root, safe_id)
    if job is None:
        raise BundleExportError(f"job not found: {safe_id}")
    approval_bytes = _approval_snapshot(source_root, safe_id)
    video = _preferred_video(job)
    try:
        destination = export_directory(destination_root, safe_id)
    except ValueError as exc:
        raise BundleExportError("export path escapes export root") from exc
    approved_root = destination_root / "approved"
    approved_root.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=approved_root))
    try:
        included_files = ["final.mp4"]
        _copy(video, temporary_dir / "final.mp4", source_root)

        for artifact_name in SUPPORTING_ARTIFACTS[:3]:
            source = job.artifacts.get(artifact_name)
            if source is not None:
                _copy(source, temporary_dir / artifact_name, source_root)
                included_files.append(artifact_name)

        receipt = job.artifacts.get("receipt.json")
        if receipt is None:
            raise BundleExportError(f"job {safe_id} is missing receipt.json")
        _copy(receipt, temporary_dir / "receipt.json", source_root)
        included_files.append("receipt.json")

        (temporary_dir / "APPROVAL.json").write_bytes(approval_bytes)
        included_files.append("APPROVAL.json")

        for artifact_name in SUPPORTING_ARTIFACTS[3:]:
            source = job.artifacts.get(artifact_name)
            if source is not None:
                _copy(source, temporary_dir / artifact_name, source_root)
                included_files.append(artifact_name)

        missing_optional = [
            artifact_name
            for artifact_name in SUPPORTING_ARTIFACTS
            if artifact_name not in job.artifacts
        ]
        manifest = build_export_manifest(job, destination, included_files, missing_optional)
        write_export_manifest(temporary_dir / "EXPORT_MANIFEST.json", manifest)

        if destination.exists() or destination.is_symlink():
            if not is_within(destination, destination_root):
                raise BundleExportError("existing export path escapes export root")
            if destination.is_symlink() or not destination.is_dir():
                raise BundleExportError("existing export path is not a safe directory")
            shutil.rmtree(destination)
        temporary_dir.replace(destination)
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise
    return ExportResult(job_id=safe_id, export_dir=destination, manifest=manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a local export bundle for an approved Shorts Factory job."
    )
    parser.add_argument("--job-id", required=True, help="Approved job ID to export")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    parser.add_argument("--export-root", default="exports", help="Local export root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = export_approved_bundle(args.job_id, args.output_root, args.export_root)
    except (BundleExportError, OSError) as exc:
        print(f"Export refused: {exc}", file=sys.stderr)
        return 1
    print(f"Approved bundle exported to {result.export_dir}")
    print("Publishing status: not_published (live publishing disabled)")
    return 0
