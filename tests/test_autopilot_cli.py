from __future__ import annotations

import json

from content_factory.autopilot.autopilot_store import AutopilotStore
from content_factory.autopilot.cli import main


def test_cli_lists_and_inspects_local_batches(tmp_path, capsys):
    store = AutopilotStore(tmp_path)
    batch_id = "ap_cli_test"
    store.write(batch_id, "plan", {
        "batch_id": batch_id,
        "mode": "dry_run",
        "status": "running",
        "created_at": "2026-06-29T00:00:00+00:00",
    })
    assert main(["--output-root", str(tmp_path), "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["batch_id"] == batch_id

    assert main(["--output-root", str(tmp_path), "status", "--batch-id", batch_id]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status == {
        "batch_id": batch_id,
        "mode": "dry_run",
        "status": "running",
        "created_at": "2026-06-29T00:00:00+00:00",
    }


def test_cli_refuses_full_autopilot(tmp_path, capsys):
    exit_code = main([
        "--output-root", str(tmp_path), "run", "--mode", "full_autopilot",
    ])
    assert exit_code == 1
    assert "Live publishing is not implemented in Phase 5A" in capsys.readouterr().err


def test_cli_accepts_output_root_after_subcommand(tmp_path, capsys):
    assert main(["list", "--output-root", str(tmp_path / "root with spaces")]) == 0
    assert json.loads(capsys.readouterr().out) == []
