from __future__ import annotations

from pathlib import Path

from content_factory.results import ResultsLedgerStore
from tests.test_results_ledger import create_ready_result_sources


def test_results_store_updates_ledger_and_reads_entries(tmp_path: Path):
    output_root = tmp_path / "output"
    export_root = tmp_path / "exports"
    create_ready_result_sources(output_root, export_root)
    store = ResultsLedgerStore(tmp_path / "results", export_root=export_root, output_root=output_root)

    first = store.record_result(
        job_id="ready-job",
        platform="youtube_shorts",
        manual_upload_url="https://example.com/manual-upload",
        metrics={"views": 100},
    )
    second = store.record_result(
        job_id="ready-job",
        platform="tiktok",
        manual_upload_url="https://example.com/manual-upload-2",
        metrics={"views": 50, "likes": 5},
    )

    ledger = store.read_ledger()
    assert ledger is not None
    assert ledger["entry_count"] == 2
    assert {entry["entry_id"] for entry in ledger["entries"]} == {
        first.entry["entry_id"],
        second.entry["entry_id"],
    }
    assert store.read_entry(first.entry["entry_id"])["job_id"] == "ready-job"
    assert len(store.entries_for_job("ready-job")) == 2
