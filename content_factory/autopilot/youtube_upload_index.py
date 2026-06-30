from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


INDEX_VERSION = "phase5b.4.youtube-upload-index.v1"
DEFAULT_INDEX = Path("output/youtube/uploads/YOUTUBE_UPLOAD_INDEX.json")


class YouTubeUploadIndexError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".youtube-upload-index.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class YouTubeUploadIndex:
    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        now: Callable[[], datetime] = _utc_now,
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.path = self.output_root / "youtube" / "uploads" / "YOUTUBE_UPLOAD_INDEX.json"
        self.now = now

    def load(self) -> dict[str, Any]:
        value = _read_json(self.path)
        if value is None:
            return {"index_version": INDEX_VERSION, "updated_at": None, "uploads": []}
        if not isinstance(value, dict) or not isinstance(value.get("uploads"), list):
            raise YouTubeUploadIndexError("YouTube upload index is invalid")
        return value

    def rebuild(self) -> dict[str, Any]:
        existing = self.load()
        existing_by_video = {
            row.get("youtube_video_id"): row
            for row in existing["uploads"]
            if isinstance(row, dict) and isinstance(row.get("youtube_video_id"), str)
        }
        records: dict[tuple[str, str], dict[str, Any]] = {}
        root = self.output_root / "youtube" / "supervised_uploads"
        if root.is_dir():
            for receipt_path in root.glob("*/02_successful_live_upload.json"):
                record = self._record(receipt_path, existing_by_video)
                if record is not None:
                    records[(record["youtube_video_id"], record["attempt_id"])] = record
        uploads = sorted(records.values(), key=lambda row: (row.get("created_at") or "", row["youtube_video_id"]))
        comparable_existing = existing.get("uploads", [])
        updated_at = existing.get("updated_at") if uploads == comparable_existing else self.now().astimezone(timezone.utc).isoformat()
        value = {"index_version": INDEX_VERSION, "updated_at": updated_at, "uploads": uploads}
        _atomic_json(self.path, value)
        return value

    def update(self, video_id: str, **changes: Any) -> dict[str, Any] | None:
        value = self.load()
        updated = None
        for row in value["uploads"]:
            if isinstance(row, dict) and row.get("youtube_video_id") == video_id:
                row.update(changes)
                updated = row
                break
        if updated is None:
            return None
        value["updated_at"] = self.now().astimezone(timezone.utc).isoformat()
        _atomic_json(self.path, value)
        return updated

    def find(self, video_id: str) -> dict[str, Any] | None:
        for row in self.load()["uploads"]:
            if isinstance(row, dict) and row.get("youtube_video_id") == video_id:
                return row
        return None

    def _record(
        self,
        success_path: Path,
        existing_by_video: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        receipt = _read_json(success_path)
        if not isinstance(receipt, dict) or receipt.get("classification") != "successful_live_upload":
            return None
        result = receipt.get("result")
        channel = receipt.get("channel")
        metadata = receipt.get("metadata_summary")
        sources = receipt.get("source_receipt_references")
        if not all(isinstance(value, dict) for value in (result, channel, metadata, sources)):
            return None
        video_id = result.get("video_id")
        attempt_id = receipt.get("attempt_id")
        if not isinstance(video_id, str) or not video_id or not isinstance(attempt_id, str) or not attempt_id:
            return None
        metadata_path = Path(str(metadata.get("metadata_path", ""))).expanduser().resolve()
        current_metadata_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest() if metadata_path.is_file() else None
        attempted_path = success_path.with_name("01_attempted_live_upload.json")
        existing = existing_by_video.get(video_id, {})
        job_id = metadata.get("source_job_id")
        hardening, hardening_hash = self._metadata_hardening_evidence(
            str(job_id) if job_id else "",
            metadata_path,
            str(receipt.get("timestamp") or ""),
            explicit=sources.get("metadata_hardening"),
        )
        metadata_hash = metadata.get("metadata_hash") or hardening_hash or current_metadata_hash
        return {
            "upload_id": f"yt_{video_id}",
            "attempt_id": attempt_id,
            "youtube_video_id": video_id,
            "youtube_url": result.get("video_url") or f"https://www.youtube.com/watch?v={video_id}",
            "channel_id": channel.get("id"),
            "channel_title": channel.get("title"),
            "job_id": job_id,
            "video_path": receipt.get("selected_video_path"),
            "metadata_path": str(metadata_path),
            "metadata_hash": metadata_hash,
            "metadata_schema_version": metadata.get("schema_version"),
            "title": metadata.get("title"),
            "privacy_status": metadata.get("privacy_status"),
            "made_for_kids": metadata.get("made_for_kids"),
            "upload_attempt_receipt": str(attempted_path) if attempted_path.is_file() else None,
            "upload_success_receipt": str(success_path.resolve()),
            "metadata_hardening_receipt": hardening,
            "credential_preflight_receipt": sources.get("credential_preflight"),
            "created_at": receipt.get("timestamp"),
            "last_verified_at": existing.get("last_verified_at"),
            "latest_verification_receipt": existing.get("latest_verification_receipt"),
            "latest_analytics_receipt": existing.get("latest_analytics_receipt"),
            "latest_country_analytics_receipt": existing.get("latest_country_analytics_receipt"),
        }

    def _metadata_hardening_evidence(
        self,
        job_id: str,
        metadata_path: Path,
        upload_timestamp: str,
        *,
        explicit: Any,
    ) -> tuple[str | None, str | None]:
        if isinstance(explicit, str) and explicit:
            explicit_path = Path(explicit).expanduser().resolve()
            value = _read_json(explicit_path)
            return (
                str(explicit_path),
                value.get("new_metadata_hash") if isinstance(value, dict) else None,
            )
        root = self.output_root / "youtube" / "metadata_hardening" / job_id
        if not job_id or not root.is_dir():
            return None, None
        matches: list[tuple[str, Path, str | None]] = []
        for path in root.glob("*_YOUTUBE_METADATA_HARDENING.json"):
            value = _read_json(path)
            if (
                isinstance(value, dict)
                and Path(str(value.get("metadata_path", ""))).expanduser().resolve() == metadata_path
            ):
                timestamp = str(value.get("timestamp") or "")
                if not upload_timestamp or not timestamp or timestamp <= upload_timestamp:
                    matches.append((timestamp, path, value.get("new_metadata_hash")))
        if not matches:
            return None, None
        _, path, metadata_hash = sorted(matches, key=lambda row: (row[0], str(row[1])))[-1]
        return str(path.resolve()), metadata_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild or inspect the local YouTube upload index.")
    parser.add_argument("--output-root", default="output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("rebuild", "show"):
        command = subparsers.add_parser(name)
        command.add_argument("--output-root", dest="output_root", default=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    index = YouTubeUploadIndex(output_root=args.output_root)
    try:
        value = index.rebuild() if args.command == "rebuild" else index.load()
    except YouTubeUploadIndexError as exc:
        print(f"YouTube upload index refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(value, indent=2, ensure_ascii=False))
    print(f"Upload index: {index.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
