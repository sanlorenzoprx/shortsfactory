from __future__ import annotations

import json
from pathlib import Path

from content_factory.config import Config
from content_factory.schemas import Idea
from content_factory.agents.app_tester import AppTester
from content_factory.agents.script_writer import ScriptWriter
from orchestrator import ContentFactoryOrchestrator


def test_mock_pipeline_creates_required_outputs(tmp_path: Path):
    config = Config(mode="mock", output_dir=tmp_path / "output")
    receipts = ContentFactoryOrchestrator(config).run_batch(batch=1, locale="en-US")
    assert len(receipts) == 1
    receipt_path = receipts[0]
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt_path.parent.name == receipt["job_id"]
    required = ["short_mp4", "thumbnail_jpg", "captions_srt", "script_txt", "verdict_json", "idea_json"]
    for key in required:
        path = Path(receipt["outputs"][key])
        assert path.exists(), key
        assert path.stat().st_size > 0, key
    assert receipt["mode"] == "mock"
    assert receipt["locale"] == "en-US"
    assert receipt["idea"]
    assert receipt["verdict"]
    assert isinstance(receipt["warnings"], list)
    assert receipt["recording"] == {"enabled": False}
    assert receipt["voiceover"] == {"status": "disabled"}
    assert receipt["music"] == {"status": "disabled"}
    assert Path(receipt["outputs"]["short_mp4"]).read_bytes()[:8].endswith(b"ftyp")
    assert Path(receipt["outputs"]["thumbnail_jpg"]).read_bytes()[:2] == b"\xff\xd8"


def test_mock_verdict_and_script_are_complete_and_deterministic():
    idea = Idea(name="Deterministic test", description="A repeatable idea")
    tester = AppTester(Config(mode="mock"))

    first = tester.run_test(idea)
    second = tester.run_test(idea)

    assert first == second
    assert first.idea == idea
    assert first.verdict_headline
    assert isinstance(first.lit_score, int)
    assert first.risk_level
    assert first.top_reason
    assert first.next_step
    assert first.source == "mock"
    assert ScriptWriter().generate_script(first) == ScriptWriter().generate_script(second)
