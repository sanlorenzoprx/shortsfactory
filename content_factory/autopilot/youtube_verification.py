from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .youtube_credentials import DEFAULT_RECEIPT
from .youtube_publisher import YouTubeCredentials
from .youtube_readonly import (
    EXPECTED_CHANNEL_ID,
    YouTubeReadOnlyError,
    atomic_new_json,
    authorize_readonly,
    load_default_credentials,
    read_object,
    redact_error,
)
from .youtube_upload_index import YouTubeUploadIndex


RECEIPT_VERSION = "phase5b.4.youtube-upload-verification.v1"
PARTS = ("snippet", "status", "contentDetails", "processingDetails")


class YouTubeVerificationTransport(Protocol):
    name: str
    videos_insert_called: bool

    def videos_list(
        self,
        *,
        access_token: str,
        scopes: tuple[str, ...],
        video_id: str,
        parts: tuple[str, ...],
    ) -> dict[str, Any]: ...


class GoogleYouTubeVerificationTransport:
    name = "google_youtube_data_api_v3"

    def __init__(self) -> None:
        self.videos_list_called = False
        self.videos_insert_called = False

    def videos_list(
        self,
        *,
        access_token: str,
        scopes: tuple[str, ...],
        video_id: str,
        parts: tuple[str, ...],
    ) -> dict[str, Any]:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(token=access_token, scopes=list(scopes))
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        try:
            self.videos_list_called = True
            response = service.videos().list(part=",".join(parts), id=video_id).execute()
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
        if not isinstance(response, dict):
            raise YouTubeReadOnlyError("YouTube videos.list returned an invalid response")
        return response


class YouTubeUploadVerifier:
    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        preflight_receipt: str | Path = DEFAULT_RECEIPT,
        transport: YouTubeVerificationTransport | None = None,
        credential_loader: Callable[[Path], YouTubeCredentials] = load_default_credentials,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.preflight_receipt = Path(preflight_receipt).expanduser().resolve()
        self.transport = transport or GoogleYouTubeVerificationTransport()
        self.credential_loader = credential_loader
        self.now = now
        self.index = YouTubeUploadIndex(output_root=self.output_root, now=now)

    def verify(
        self,
        *,
        expected_channel_id: str,
        video_id: str | None = None,
        success_receipt: str | Path | None = None,
    ) -> dict[str, Any]:
        source_success = Path(success_receipt).expanduser().resolve() if success_receipt else None
        if source_success:
            source = read_object(source_success, "successful upload receipt")
            if source.get("classification") != "successful_live_upload":
                raise YouTubeReadOnlyError("source receipt is not a successful upload receipt")
            result = source.get("result")
            receipt_video_id = result.get("video_id") if isinstance(result, dict) else None
            if not isinstance(receipt_video_id, str) or not receipt_video_id:
                raise YouTubeReadOnlyError("successful upload receipt has no video ID")
            if video_id and video_id != receipt_video_id:
                raise YouTubeReadOnlyError("video ID does not match successful upload receipt")
            video_id = receipt_video_id
        if not isinstance(video_id, str) or not video_id.strip() or Path(video_id).name != video_id:
            raise YouTubeReadOnlyError("one valid YouTube video ID is required")
        video_id = video_id.strip()
        self.index.rebuild()
        indexed = self.index.find(video_id) or {}
        source_success_path = source_success or (
            Path(indexed["upload_success_receipt"]) if indexed.get("upload_success_receipt") else None
        )
        sources = {
            "attempted": indexed.get("upload_attempt_receipt"),
            "successful": str(source_success_path) if source_success_path else None,
            "metadata_hardening": indexed.get("metadata_hardening_receipt"),
            "credential_preflight": str(self.preflight_receipt),
        }
        base = {
            "receipt_version": RECEIPT_VERSION,
            "timestamp": self.now().astimezone(timezone.utc).isoformat(),
            "video_id": video_id,
            "youtube_url": indexed.get("youtube_url") or f"https://www.youtube.com/watch?v={video_id}",
            "channel_id": indexed.get("channel_id"),
            "expected_channel_id": expected_channel_id,
            "job_id": indexed.get("job_id"),
            "source_upload_receipts": sources,
            "request_type": "videos.list",
            "parts_requested": list(PARTS),
        }
        try:
            access = authorize_readonly(
                preflight_receipt=self.preflight_receipt,
                expected_channel_id=expected_channel_id,
                require_analytics_scope=False,
                credential_loader=self.credential_loader,
                now=self.now,
            )
        except Exception as exc:
            receipt = self._receipt(base, status="blocked", api_called=False, error=redact_error(exc))
            path = self._write(video_id, receipt)
            self.index.update(video_id, latest_verification_receipt=str(path))
            return {**receipt, "receipt_path": str(path)}
        base["channel_id"] = access.channel_id
        try:
            response = self.transport.videos_list(
                access_token=access.credentials.access_token,
                scopes=access.credentials.scopes,
                video_id=video_id,
                parts=PARTS,
            )
            items = response.get("items", []) if isinstance(response, dict) else []
            item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else None
            if item is None:
                receipt = self._receipt(base, status="not_found", api_called=True, found=False)
            else:
                snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
                status = item.get("status") if isinstance(item.get("status"), dict) else {}
                content = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
                processing = item.get("processingDetails") if isinstance(item.get("processingDetails"), dict) else {}
                channel_matches = snippet.get("channelId") == EXPECTED_CHANNEL_ID
                receipt = self._receipt(
                    base,
                    status="verified" if channel_matches else "channel_mismatch",
                    api_called=True,
                    found=True,
                    item={
                        "title": snippet.get("title"),
                        "privacy_status": status.get("privacyStatus"),
                        "upload_status": status.get("uploadStatus"),
                        "processing_status": processing.get("processingStatus"),
                        "embeddable": status.get("embeddable"),
                        "public_stats_viewable": status.get("publicStatsViewable"),
                        "made_for_kids": item.get("madeForKids"),
                        "self_declared_made_for_kids": item.get("selfDeclaredMadeForKids"),
                        "thumbnails_present": bool(snippet.get("thumbnails")),
                        "duration": content.get("duration"),
                        "raw_response_redacted": {
                            "id": item.get("id"),
                            "channel_id": snippet.get("channelId"),
                            "privacy_status": status.get("privacyStatus"),
                            "upload_status": status.get("uploadStatus"),
                            "processing_status": processing.get("processingStatus"),
                        },
                    },
                    error=None if channel_matches else "video channel does not match Ghost Town Test",
                )
        except Exception as exc:
            receipt = self._receipt(
                base,
                status="failed",
                api_called=bool(getattr(self.transport, "videos_list_called", True)),
                error=redact_error(exc, (access.credentials.access_token,)),
            )
        path = self._write(video_id, receipt)
        changes: dict[str, Any] = {"latest_verification_receipt": str(path)}
        if receipt["verification_status"] == "verified":
            changes["last_verified_at"] = receipt["timestamp"]
        self.index.update(video_id, **changes)
        return {**receipt, "receipt_path": str(path)}

    def _write(self, video_id: str, receipt: dict[str, Any]) -> Path:
        timestamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = (
            self.output_root / "youtube" / "verifications" / video_id
            / f"{timestamp}_YOUTUBE_UPLOAD_VERIFICATION.json"
        )
        atomic_new_json(path, receipt)
        return path

    def _receipt(
        self,
        base: dict[str, Any],
        *,
        status: str,
        api_called: bool,
        found: bool = False,
        item: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        values = item or {}
        return {
            **base,
            "verification_status": status,
            "found": found,
            "title": values.get("title"),
            "privacy_status": values.get("privacy_status"),
            "upload_status": values.get("upload_status"),
            "processing_status": values.get("processing_status"),
            "embeddable": values.get("embeddable"),
            "public_stats_viewable": values.get("public_stats_viewable"),
            "made_for_kids": values.get("made_for_kids"),
            "self_declared_made_for_kids": values.get("self_declared_made_for_kids"),
            "thumbnails_present": values.get("thumbnails_present", False),
            "duration": values.get("duration"),
            "raw_response_redacted": values.get("raw_response_redacted", {}),
            "api_called": api_called,
            "videos_insert_called": bool(getattr(self.transport, "videos_insert_called", False)),
            "secrets_recorded": False,
            "error": error,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify one supervised YouTube upload without publishing.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video-id")
    source.add_argument("--from-success-receipt")
    parser.add_argument("--expected-channel-id", required=True)
    parser.add_argument("--preflight-receipt", default=str(DEFAULT_RECEIPT))
    parser.add_argument("--output-root", default="output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verifier = YouTubeUploadVerifier(
        output_root=args.output_root,
        preflight_receipt=args.preflight_receipt,
    )
    try:
        receipt = verifier.verify(
            expected_channel_id=args.expected_channel_id,
            video_id=args.video_id,
            success_receipt=args.from_success_receipt,
        )
    except YouTubeReadOnlyError as exc:
        print(f"YouTube upload verification refused: {exc}", file=sys.stderr)
        return 1
    print(f"Verification status: {receipt['verification_status']}")
    print(f"Verification receipt: {receipt['receipt_path']}")
    return 0 if receipt["verification_status"] in {"verified", "not_found"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
