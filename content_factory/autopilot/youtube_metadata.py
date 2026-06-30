from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import parse_qsl, urlparse

from content_factory.mission_control.job_index import is_within


SCHEMA_VERSION = "youtube_upload_metadata.v1"
RECEIPT_VERSION = "phase5b.3.youtube-metadata-hardening.v1"
CANONICAL_TAGS = (
    "business ideas",
    "startup validation",
    "ghost town test",
    "entrepreneurship",
    "market validation",
)
PRIVACY_STATUSES = {"private", "unlisted", "public"}
SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|authorization\s*:|bearer\s+|auth[_ -]?code)"
)
AUTH_URL_PATTERN = re.compile(r"(?i)(oauth|/authorize(?:[/?#]|$)|accounts\.google\.com|token_uri)")
URL_PATTERN = re.compile(r"https?://[^\s\"<>]+", re.I)


class YouTubeMetadataError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def normalize_hashtags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise YouTubeMetadataError("hashtags must be a list of strings")
    cleaned = []
    for item in value:
        tag = item.strip()
        if not tag:
            continue
        tag = "#" + tag.lstrip("#").strip()
        if tag != "#":
            cleaned.append(tag)
    return _dedupe(cleaned)


def normalize_tags(value: Any, *, include_canonical: bool) -> list[str]:
    if value is None:
        source: list[str] = []
    elif not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise YouTubeMetadataError("tags must be a list of strings")
    else:
        source = value
    cleaned = []
    for item in source:
        tag = " ".join(item.lstrip("#").strip().split())
        if tag:
            cleaned.append(tag)
    if include_canonical:
        cleaned.extend(CANONICAL_TAGS)
    return _dedupe(cleaned)


def validate_website_url(value: str | None) -> str | None:
    website = _clean_text(value)
    if not website:
        return None
    parsed = urlparse(website)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or AUTH_URL_PATTERN.search(website)
    ):
        raise YouTubeMetadataError("website_url must be a safe public http/https URL")
    suspicious_query = {
        "access_token", "refresh_token", "client_secret", "authorization", "code", "token"
    }
    if any(key.casefold() in suspicious_query for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise YouTubeMetadataError("website_url must not contain authentication parameters")
    return website


def _reject_sensitive_text(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    has_auth_url = any(AUTH_URL_PATTERN.search(url) for url in URL_PATTERN.findall(encoded))
    if SECRET_PATTERN.search(encoded) or has_auth_url:
        raise YouTubeMetadataError("metadata must not contain secrets or authentication URLs")


def read_metadata_json(path: str | Path, *, allow_bom_repair: bool = False) -> tuple[dict[str, Any], bool]:
    metadata_path = Path(path).expanduser().resolve()
    if not metadata_path.is_file():
        raise YouTubeMetadataError("YouTube metadata is missing")
    try:
        raw = metadata_path.read_bytes()
    except OSError as exc:
        raise YouTubeMetadataError("YouTube metadata could not be read") from exc
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom and not allow_bom_repair:
        raise YouTubeMetadataError(
            "YouTube metadata contains a UTF-8 BOM; run youtube_metadata.py harden for this job"
        )
    try:
        decoded = raw.decode("utf-8-sig" if allow_bom_repair else "utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise YouTubeMetadataError(
            "YouTube metadata is not valid UTF-8 JSON; run youtube_metadata.py harden for this job"
        ) from exc
    if not isinstance(value, dict):
        raise YouTubeMetadataError("YouTube metadata must contain a JSON object")
    return value, had_bom


def _atomic_utf8_json(path: Path, value: dict[str, Any]) -> bytes:
    encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise YouTubeMetadataError("refusing to write metadata with a UTF-8 BOM")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".youtube-metadata.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return encoded


def _atomic_new_receipt(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".youtube-metadata-receipt.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class YouTubeUploadMetadataV1:
    schema_version: str
    platform: str
    source_job_id: str
    title: str
    description: str
    caption: str
    hashtags: tuple[str, ...]
    tags: tuple[str, ...]
    category_id: str
    privacy_status: str
    made_for_kids: bool
    video: str
    publish_at: str | None
    thumbnail: str | None
    captions: str | None
    website_url: str | None
    cta_text: str | None
    source_receipt_references: dict[str, str]
    generated_at: str
    locale: str | None = None
    notify_subscribers: bool = False
    status: str = "supervised_upload_ready"
    live_publish_enabled: bool = False

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        *,
        allow_legacy: bool = False,
        source_receipt_references: dict[str, str] | None = None,
        generated_at: str | None = None,
    ) -> "YouTubeUploadMetadataV1":
        schema = value.get("schema_version")
        if schema is not None and schema != SCHEMA_VERSION:
            raise YouTubeMetadataError(f"unsupported YouTube metadata schema_version: {schema}")
        if schema is None and not allow_legacy:
            raise YouTubeMetadataError("metadata schema_version is missing")
        missing = [
            name for name in ("privacy_status", "made_for_kids", "tags")
            if name not in value
        ]
        if missing:
            job_id = _clean_text(value.get("source_job_id")) or "<job_id>"
            raise YouTubeMetadataError(
                "metadata hardening is required; missing "
                + ", ".join(missing)
                + f". Run: python youtube_metadata.py harden --job-id {job_id}"
            )
        if schema == SCHEMA_VERSION:
            raw_tags = value.get("tags")
            raw_hashtags = value.get("hashtags", [])
            if (
                not isinstance(raw_tags, list)
                or any(not isinstance(tag, str) or not tag.strip() or tag.strip().startswith("#") for tag in raw_tags)
            ):
                raise YouTubeMetadataError("tags must be clean strings without a leading #")
            if (
                not isinstance(raw_hashtags, list)
                or any(not isinstance(tag, str) or not tag.strip().startswith("#") for tag in raw_hashtags)
            ):
                raise YouTubeMetadataError("hashtags must retain a leading #")
        metadata = cls(
            schema_version=SCHEMA_VERSION,
            platform=_clean_text(value.get("platform")),
            source_job_id=_clean_text(value.get("source_job_id")),
            title=_clean_text(value.get("title")),
            description=_clean_text(value.get("description")),
            caption=_clean_text(value.get("caption")),
            hashtags=tuple(normalize_hashtags(value.get("hashtags", []))),
            tags=tuple(normalize_tags(value.get("tags"), include_canonical=False)),
            category_id=_clean_text(value.get("category_id")) or "22",
            privacy_status=_clean_text(value.get("privacy_status")),
            made_for_kids=value.get("made_for_kids"),
            video=_clean_text(value.get("video")),
            publish_at=_clean_text(value.get("publish_at")) or None,
            thumbnail=_clean_text(value.get("thumbnail")) or None,
            captions=_clean_text(value.get("captions")) or None,
            website_url=validate_website_url(value.get("website_url")),
            cta_text=_clean_text(value.get("cta_text")) or None,
            source_receipt_references=dict(
                value.get("source_receipt_references")
                if isinstance(value.get("source_receipt_references"), dict)
                else source_receipt_references or {}
            ),
            generated_at=_clean_text(value.get("generated_at")) or generated_at or _utc_now().isoformat(),
            locale=_clean_text(value.get("locale")) or None,
            notify_subscribers=value.get("notify_subscribers", False),
            status=_clean_text(value.get("status")) or "supervised_upload_ready",
            live_publish_enabled=value.get("live_publish_enabled", False),
        )
        metadata.validate()
        return metadata

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise YouTubeMetadataError("invalid YouTube metadata schema_version")
        if self.platform != "youtube_shorts":
            raise YouTubeMetadataError("platform must be youtube_shorts")
        if not self.source_job_id:
            raise YouTubeMetadataError("source_job_id is required")
        if not self.title or len(self.title) > 100:
            raise YouTubeMetadataError("title must contain 1 to 100 characters")
        if not self.description or len(self.description) > 5000:
            raise YouTubeMetadataError("description must contain 1 to 5000 characters")
        if self.privacy_status not in PRIVACY_STATUSES:
            raise YouTubeMetadataError("privacy_status must be private, unlisted, or public")
        if not isinstance(self.made_for_kids, bool):
            raise YouTubeMetadataError("made_for_kids must be an explicit boolean")
        if not self.video:
            raise YouTubeMetadataError("video path is required")
        if not self.tags:
            raise YouTubeMetadataError("at least one clean YouTube tag is required")
        if any(not tag.strip() or tag.startswith("#") for tag in self.tags):
            raise YouTubeMetadataError("tags must be clean strings without a leading #")
        if any(not hashtag.startswith("#") for hashtag in self.hashtags):
            raise YouTubeMetadataError("hashtags must retain a leading #")
        if not self.category_id.isdigit():
            raise YouTubeMetadataError("category_id must be numeric")
        if self.publish_at and self.privacy_status != "private":
            raise YouTubeMetadataError("publish_at is allowed only when privacy_status is private")
        if self.publish_at:
            try:
                parsed_publish_at = datetime.fromisoformat(self.publish_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise YouTubeMetadataError("publish_at must be an ISO-8601 datetime") from exc
            if parsed_publish_at.tzinfo is None or parsed_publish_at.utcoffset() is None:
                raise YouTubeMetadataError("publish_at must include a timezone")
        if not isinstance(self.notify_subscribers, bool):
            raise YouTubeMetadataError("notify_subscribers must be boolean")
        if self.live_publish_enabled is not False:
            raise YouTubeMetadataError("metadata hardening must not enable live publishing")
        if not self.generated_at:
            raise YouTubeMetadataError("generated_at is required")
        if (
            not self.source_receipt_references
            or any(not isinstance(key, str) or not isinstance(value, str) or not value for key, value in self.source_receipt_references.items())
        ):
            raise YouTubeMetadataError("source_receipt_references must contain trusted receipt paths")
        _reject_sensitive_text(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["hashtags"] = list(self.hashtags)
        value["tags"] = list(self.tags)
        return value


@dataclass(frozen=True)
class MetadataHardeningResult:
    job_id: str
    metadata_path: str
    receipt_path: str
    video_path: str
    supervised_upload_command: str


class YouTubeMetadataHardener:
    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        now: Callable[[], datetime] = _utc_now,
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.now = now

    def harden(
        self,
        *,
        job_id: str,
        privacy_status: str = "private",
        made_for_kids: bool = False,
        brand_name: str = "Ghost Town Test",
        website_url: str | None = None,
        cta_text: str | None = None,
    ) -> MetadataHardeningResult:
        if not job_id or Path(job_id).name != job_id:
            raise YouTubeMetadataError("invalid job_id")
        job_dir = (self.output_root / "jobs" / job_id).resolve()
        jobs_root = (self.output_root / "jobs").resolve()
        if not is_within(job_dir, jobs_root) or not job_dir.is_dir():
            raise YouTubeMetadataError(f"trusted generated job is missing: {job_id}")

        receipt_path = job_dir / "receipt.json"
        generation_receipt = self._read_object(receipt_path, "generation/content receipt")
        if generation_receipt.get("job_id") != job_id:
            raise YouTubeMetadataError("generation/content receipt does not match job_id")
        publisher_plan_path = job_dir / "publish" / "publisher_plan.json"
        publisher_plan = self._read_object(publisher_plan_path, "publisher plan")
        if publisher_plan.get("source_job_id") != job_id:
            raise YouTubeMetadataError("publisher plan does not match job_id")
        platforms = publisher_plan.get("platforms")
        relative_metadata = platforms.get("youtube_shorts") if isinstance(platforms, dict) else None
        if not isinstance(relative_metadata, str) or not relative_metadata:
            raise YouTubeMetadataError("publisher plan does not reference generated YouTube metadata")
        metadata_path = (publisher_plan_path.parent / relative_metadata).resolve()
        if not is_within(metadata_path, job_dir):
            raise YouTubeMetadataError("publisher plan YouTube metadata path escapes the generated job")
        legacy, previous_had_bom = read_metadata_json(metadata_path, allow_bom_repair=True)
        if legacy.get("source_job_id") != job_id:
            raise YouTubeMetadataError("generated YouTube metadata does not match job_id")

        video_value = _clean_text(legacy.get("video"))
        video_path = (metadata_path.parent / video_value).resolve() if video_value else Path()
        outputs = generation_receipt.get("outputs")
        if (
            not video_value
            or not video_path.is_file()
            or not isinstance(outputs, dict)
            or not self._listed_output(video_path, outputs.values(), receipt_path.parent)
        ):
            raise YouTubeMetadataError("generated YouTube metadata video is not bound to the job receipt")

        safe_website = validate_website_url(website_url)
        safe_cta = _clean_text(cta_text) or None
        safe_brand = _clean_text(brand_name)
        _reject_sensitive_text({"cta_text": safe_cta, "brand_name": safe_brand})

        description = _clean_text(legacy.get("description"))
        additions = [value for value in (safe_cta, safe_website) if value and value not in description]
        if additions:
            description = description.rstrip() + "\n\n" + "\n".join(additions)

        source_refs = {
            "generation_content_receipt": str(receipt_path),
            "publisher_plan": str(publisher_plan_path),
            "generated_youtube_metadata": str(metadata_path),
        }
        generated_at = self.now().astimezone(timezone.utc).isoformat()
        value = {
            **legacy,
            "schema_version": SCHEMA_VERSION,
            "platform": "youtube_shorts",
            "source_job_id": job_id,
            "title": _clean_text(legacy.get("title")),
            "description": description,
            "caption": _clean_text(legacy.get("caption")),
            "hashtags": normalize_hashtags(legacy.get("hashtags", [])),
            "tags": normalize_tags(legacy.get("tags", []), include_canonical=True),
            "category_id": _clean_text(legacy.get("category_id")) or "22",
            "privacy_status": privacy_status,
            "made_for_kids": made_for_kids,
            "publish_at": _clean_text(legacy.get("publish_at")) or (
                _clean_text(legacy.get("schedule_window", {}).get("publish_at"))
                if isinstance(legacy.get("schedule_window"), dict) else None
            ),
            "website_url": safe_website,
            "cta_text": safe_cta,
            "source_receipt_references": source_refs,
            "generated_at": generated_at,
            "status": "supervised_upload_ready",
            "live_publish_enabled": False,
        }
        model = YouTubeUploadMetadataV1.from_dict(value)
        previous_bytes = metadata_path.read_bytes()
        new_bytes = _atomic_utf8_json(metadata_path, model.to_dict())
        persisted, persisted_had_bom = read_metadata_json(metadata_path)
        YouTubeUploadMetadataV1.from_dict(persisted)
        if persisted_had_bom:
            raise YouTubeMetadataError("metadata UTF-8 no-BOM verification failed")

        timestamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        hardening_receipt_path = (
            self.output_root / "youtube" / "metadata_hardening" / job_id
            / f"{timestamp}_YOUTUBE_METADATA_HARDENING.json"
        )
        hardening_receipt = {
            "receipt_version": RECEIPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "timestamp": generated_at,
            "job_id": job_id,
            "metadata_path": str(metadata_path),
            "previous_metadata_hash": _sha256(previous_bytes),
            "new_metadata_hash": _sha256(new_bytes),
            "privacy_status": model.privacy_status,
            "made_for_kids": model.made_for_kids,
            "tags": list(model.tags),
            "category_id": model.category_id,
            "website_url_included": safe_website is not None,
            "cta_included": safe_cta is not None,
            "brand_name": safe_brand or None,
            "utf8_without_bom": True,
            "previous_metadata_had_bom": previous_had_bom,
            "source_receipt_references": source_refs,
            "secrets_recorded": False,
        }
        _reject_sensitive_text(hardening_receipt)
        _atomic_new_receipt(hardening_receipt_path, hardening_receipt)
        command = self.supervised_upload_command(video_path, metadata_path)
        return MetadataHardeningResult(
            job_id=job_id,
            metadata_path=str(metadata_path),
            receipt_path=str(hardening_receipt_path),
            video_path=str(video_path),
            supervised_upload_command=command,
        )

    def supervised_upload_command(self, video_path: Path, metadata_path: Path) -> str:
        return (
            f'python youtube_supervised_upload.py --video "{video_path}" '
            f'--metadata "{metadata_path}" '
            f'--output-root "{self.output_root}" '
            "--confirm-channel-id UCIzMYpBt3WdSXZBrvoE7eCg "
            "--confirm-live-upload --confirm-quota-reviewed --confirm-policy-reviewed"
        )

    @staticmethod
    def _read_object(path: Path, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise YouTubeMetadataError(f"{label} is missing")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise YouTubeMetadataError(f"{label} must contain valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise YouTubeMetadataError(f"{label} must contain a JSON object")
        return value

    @staticmethod
    def _listed_output(target: Path, values: Any, anchor: Path) -> bool:
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            path = Path(value).expanduser()
            candidates = [path.resolve()] if path.is_absolute() else [
                (anchor / path).resolve(),
                (Path.cwd() / path).resolve(),
            ]
            if target.resolve() in candidates:
                return True
        return False


def _bool_arg(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harden generated YouTube metadata without uploading.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    harden = subparsers.add_parser("harden", help="Harden one generated job's YouTube metadata")
    harden.add_argument("--job-id", required=True)
    harden.add_argument("--output-root", default="output")
    harden.add_argument("--privacy-status", choices=sorted(PRIVACY_STATUSES), default="private")
    harden.add_argument("--made-for-kids", type=_bool_arg, default=False)
    harden.add_argument("--brand-name", default="Ghost Town Test")
    harden.add_argument("--website-url", nargs="?", const="", default="")
    harden.add_argument("--cta-text", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = YouTubeMetadataHardener(output_root=args.output_root).harden(
            job_id=args.job_id,
            privacy_status=args.privacy_status,
            made_for_kids=args.made_for_kids,
            brand_name=args.brand_name,
            website_url=args.website_url,
            cta_text=args.cta_text,
        )
    except YouTubeMetadataError as exc:
        print(f"YouTube metadata hardening refused: {exc}", file=sys.stderr)
        return 1
    print(f"Metadata: {result.metadata_path}")
    print(f"Hardening receipt: {result.receipt_path}")
    print("Next supervised upload command:")
    print(result.supervised_upload_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
