from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .youtube_credentials import DEFAULT_RECEIPT
from .youtube_publisher import YouTubeCredentials
from .youtube_readonly import (
    EXPECTED_CHANNEL_ID,
    MissingAnalyticsScopeError,
    atomic_new_json,
    authorize_readonly,
    load_default_credentials,
    redact_error,
)
from .youtube_upload_index import YouTubeUploadIndex


RECEIPT_VERSION = "phase5b.4.youtube-analytics-snapshot.v1"
PERFORMANCE_METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "likes",
    "comments",
    "shares",
)
COUNTRY_METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "likes",
)


class AnalyticsUnsupportedError(ValueError):
    pass


class YouTubeAnalyticsTransport(Protocol):
    name: str
    videos_insert_called: bool

    def query(
        self,
        *,
        access_token: str,
        scopes: tuple[str, ...],
        start_date: str,
        end_date: str,
        metrics: tuple[str, ...],
        dimensions: tuple[str, ...],
        filters: str,
        sort: str | None,
        max_results: int | None,
    ) -> dict[str, Any]: ...


class GoogleYouTubeAnalyticsTransport:
    name = "google_youtube_analytics_api_v2"

    def __init__(self) -> None:
        self.query_calls = 0
        self.videos_insert_called = False

    def query(
        self,
        *,
        access_token: str,
        scopes: tuple[str, ...],
        start_date: str,
        end_date: str,
        metrics: tuple[str, ...],
        dimensions: tuple[str, ...],
        filters: str,
        sort: str | None,
        max_results: int | None,
    ) -> dict[str, Any]:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(token=access_token, scopes=list(scopes))
        service = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
        arguments: dict[str, Any] = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": ",".join(metrics),
            "filters": filters,
        }
        if dimensions:
            arguments["dimensions"] = ",".join(dimensions)
        if sort:
            arguments["sort"] = sort
        if max_results is not None:
            arguments["maxResults"] = max_results
        try:
            self.query_calls += 1
            response = service.reports().query(**arguments).execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 400:
                raise AnalyticsUnsupportedError("YouTube Analytics rejected this metric/dimension combination") from exc
            raise
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
        if not isinstance(response, dict):
            raise ValueError("YouTube Analytics returned an invalid response")
        return response


@dataclass(frozen=True)
class AnalyticsReport:
    report_type: str
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...]
    sort: str | None
    max_results: int | None
    suffix: str


REPORTS = (
    AnalyticsReport(
        report_type="video_performance",
        metrics=PERFORMANCE_METRICS,
        dimensions=(),
        sort=None,
        max_results=None,
        suffix="YOUTUBE_ANALYTICS_SNAPSHOT.json",
    ),
    AnalyticsReport(
        report_type="country_breakdown",
        metrics=COUNTRY_METRICS,
        dimensions=("country",),
        sort="-views",
        max_results=25,
        suffix="YOUTUBE_COUNTRY_ANALYTICS_SNAPSHOT.json",
    ),
)


class YouTubeAnalyticsSnapshotter:
    def __init__(
        self,
        *,
        output_root: str | Path = "output",
        preflight_receipt: str | Path = DEFAULT_RECEIPT,
        transport: YouTubeAnalyticsTransport | None = None,
        credential_loader: Callable[[Path], YouTubeCredentials] = load_default_credentials,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.preflight_receipt = Path(preflight_receipt).expanduser().resolve()
        self.transport = transport or GoogleYouTubeAnalyticsTransport()
        self.credential_loader = credential_loader
        self.now = now
        self.index = YouTubeUploadIndex(output_root=self.output_root, now=now)

    def snapshot(
        self,
        *,
        video_id: str,
        days: int | None = None,
        expected_channel_id: str = EXPECTED_CHANNEL_ID,
    ) -> dict[str, dict[str, Any]]:
        if not video_id or Path(video_id).name != video_id:
            raise ValueError("one valid YouTube video ID is required")
        if days is not None and days < 1:
            raise ValueError("days must be at least 1")
        self.index.rebuild()
        indexed = self.index.find(video_id) or {}
        start_date, end_date, day_count = self._date_range(indexed, days)
        base = {
            "receipt_version": RECEIPT_VERSION,
            "timestamp": self.now().astimezone(timezone.utc).isoformat(),
            "video_id": video_id,
            "youtube_url": indexed.get("youtube_url") or f"https://www.youtube.com/watch?v={video_id}",
            "channel_id": indexed.get("channel_id"),
            "job_id": indexed.get("job_id"),
            "date_range": {"start_date": start_date, "end_date": end_date, "days": day_count},
            "filters": f"video=={video_id}",
            "source_upload_receipt": indexed.get("upload_success_receipt"),
        }
        try:
            access = authorize_readonly(
                preflight_receipt=self.preflight_receipt,
                expected_channel_id=expected_channel_id,
                require_analytics_scope=True,
                credential_loader=self.credential_loader,
                now=self.now,
            )
        except MissingAnalyticsScopeError as exc:
            results = self._blocked_reports(base, "blocked_missing_analytics_scope", redact_error(exc))
            self._update_index(video_id, results)
            return results
        except Exception as exc:
            results = self._blocked_reports(base, "blocked", redact_error(exc))
            self._update_index(video_id, results)
            return results

        base["channel_id"] = access.channel_id
        results: dict[str, dict[str, Any]] = {}
        for report in REPORTS:
            calls_before = self._transport_call_count()
            try:
                response = self.transport.query(
                    access_token=access.credentials.access_token,
                    scopes=access.credentials.scopes,
                    start_date=start_date,
                    end_date=end_date,
                    metrics=report.metrics,
                    dimensions=report.dimensions,
                    filters=base["filters"],
                    sort=report.sort,
                    max_results=report.max_results,
                )
                rows = self._rows(response)
                status = "available" if rows else "empty"
                receipt = self._receipt(
                    base,
                    report,
                    snapshot_status=status,
                    rows=rows,
                    totals=self._totals(rows, report),
                    api_called=True,
                    error=None,
                )
            except AnalyticsUnsupportedError as exc:
                receipt = self._receipt(
                    base,
                    report,
                    snapshot_status="blocked_or_unsupported",
                    rows=[],
                    totals={},
                    api_called=self._transport_was_called(calls_before),
                    error=redact_error(exc, (access.credentials.access_token,)),
                )
            except Exception as exc:
                receipt = self._receipt(
                    base,
                    report,
                    snapshot_status="failed",
                    rows=[],
                    totals={},
                    api_called=self._transport_was_called(calls_before),
                    error=redact_error(exc, (access.credentials.access_token,)),
                )
            path = self._write(video_id, report, receipt)
            results[report.report_type] = {**receipt, "receipt_path": str(path)}
        self._update_index(video_id, results)
        return results

    def _blocked_reports(
        self,
        base: dict[str, Any],
        status: str,
        error: str,
    ) -> dict[str, dict[str, Any]]:
        results = {}
        for report in REPORTS:
            receipt = self._receipt(
                base,
                report,
                snapshot_status=status,
                rows=[],
                totals={},
                api_called=False,
                error=error,
            )
            path = self._write(base["video_id"], report, receipt)
            results[report.report_type] = {**receipt, "receipt_path": str(path)}
        return results

    def _write(self, video_id: str, report: AnalyticsReport, receipt: dict[str, Any]) -> Path:
        timestamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.output_root / "youtube" / "analytics" / video_id / f"{timestamp}_{report.suffix}"
        atomic_new_json(path, receipt)
        return path

    def _receipt(
        self,
        base: dict[str, Any],
        report: AnalyticsReport,
        *,
        snapshot_status: str,
        rows: list[dict[str, Any]],
        totals: dict[str, Any],
        api_called: bool,
        error: str | None,
    ) -> dict[str, Any]:
        return {
            **base,
            "report_type": report.report_type,
            "metrics_requested": list(report.metrics),
            "dimensions_requested": list(report.dimensions),
            "sort": report.sort,
            "max_results": report.max_results,
            "rows": rows,
            "totals": totals,
            "snapshot_status": snapshot_status,
            "api_called": api_called,
            "videos_insert_called": bool(getattr(self.transport, "videos_insert_called", False)),
            "secrets_recorded": False,
            "error": error,
        }

    def _update_index(self, video_id: str, results: dict[str, dict[str, Any]]) -> None:
        performance = results.get("video_performance", {})
        country = results.get("country_breakdown", {})
        self.index.update(
            video_id,
            latest_analytics_receipt=performance.get("receipt_path"),
            latest_country_analytics_receipt=country.get("receipt_path"),
        )

    def _transport_call_count(self) -> int | None:
        calls = getattr(self.transport, "calls", None)
        if isinstance(calls, list):
            return len(calls)
        query_calls = getattr(self.transport, "query_calls", None)
        return query_calls if isinstance(query_calls, int) else None

    def _transport_was_called(self, before: int | None) -> bool:
        after = self._transport_call_count()
        return True if before is None or after is None else after > before

    def _date_range(self, indexed: dict[str, Any], days: int | None) -> tuple[str, str, int]:
        today = self.now().astimezone(timezone.utc).date()
        if days is not None:
            start = today - timedelta(days=days - 1)
        else:
            created = indexed.get("created_at")
            try:
                start = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                start = today
            if start > today:
                start = today
        return start.isoformat(), today.isoformat(), (today - start).days + 1

    @staticmethod
    def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
        raw_headers = response.get("columnHeaders", [])
        headers = [row.get("name") for row in raw_headers if isinstance(row, dict) and row.get("name")]
        raw_rows = response.get("rows", [])
        if not headers or not isinstance(raw_rows, list):
            return []
        return [
            {name: value for name, value in zip(headers, row)}
            for row in raw_rows if isinstance(row, list)
        ]

    @staticmethod
    def _totals(rows: list[dict[str, Any]], report: AnalyticsReport) -> dict[str, Any]:
        if report.report_type == "video_performance" and rows:
            return {metric: rows[0].get(metric) for metric in report.metrics}
        return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture read-only YouTube analytics snapshots without uploading.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--days", type=int)
    parser.add_argument("--expected-channel-id", default=EXPECTED_CHANNEL_ID)
    parser.add_argument("--preflight-receipt", default=str(DEFAULT_RECEIPT))
    parser.add_argument("--output-root", default="output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshotter = YouTubeAnalyticsSnapshotter(
        output_root=args.output_root,
        preflight_receipt=args.preflight_receipt,
    )
    try:
        results = snapshotter.snapshot(
            video_id=args.video_id,
            days=args.days,
            expected_channel_id=args.expected_channel_id,
        )
    except ValueError as exc:
        print(f"YouTube analytics snapshot refused: {exc}", file=sys.stderr)
        return 1
    for name in ("video_performance", "country_breakdown"):
        receipt = results[name]
        print(f"{name}: {receipt['snapshot_status']}")
        print(f"Receipt: {receipt['receipt_path']}")
    statuses = {receipt["snapshot_status"] for receipt in results.values()}
    return 0 if statuses <= {"available", "empty", "blocked_or_unsupported"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
