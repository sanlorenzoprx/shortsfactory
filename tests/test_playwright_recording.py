from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import orchestrator as orchestrator_module
from content_factory.config import Config
from content_factory.integrations.playwright_recorder import AppRecordingResult
from orchestrator import ContentFactoryOrchestrator, parse_args


def _fast_orchestrator(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> ContentFactoryOrchestrator:
    orchestrator = ContentFactoryOrchestrator(config)

    def create_short(_script, _verdict, job_dir: Path) -> Path:
        path = job_dir / "short.mp4"
        path.write_bytes(b"test-mp4")
        return path

    monkeypatch.setattr(orchestrator.video, "create_short", create_short)
    return orchestrator


def test_recording_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_RECORDING_ENABLED", raising=False)
    assert Config().playwright_recording_enabled is False


@pytest.mark.parametrize("mode", ["mock", "api"])
def test_disabled_recording_is_in_receipt_and_never_calls_recorder(
    mode, tmp_path, monkeypatch
):
    config = Config(
        mode=mode,
        lit_api_url="http://127.0.0.1:1/api/verdict",
        lit_api_timeout_seconds=0.01,
        output_dir=tmp_path / mode,
        playwright_recording_enabled=False,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)

    def recorder_was_not_requested(**_kwargs):
        raise AssertionError("recorder should not run without --record-app")

    monkeypatch.setattr(
        orchestrator_module, "record_lit_app_flow", recorder_was_not_requested
    )
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["recording"] == {"enabled": False}
    assert Path(receipt["outputs"]["short_mp4"]).exists()


def test_recorder_failure_does_not_break_pipeline_and_writes_warning(
    tmp_path, monkeypatch
):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        playwright_recording_enabled=True,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)

    def failed_recorder(**kwargs):
        return AppRecordingResult(
            success=False,
            raw_video_path=None,
            normalized_video_path=None,
            screenshot_path=None,
            warnings=["app_recording_failed: LIT app did not become ready before timeout"],
            metadata={
                "enabled": True,
                "source": "playwright",
                "app_url": kwargs["app_url"],
                "status": "failed",
                "error_code": "timeout",
            },
        )

    monkeypatch.setattr(orchestrator_module, "record_lit_app_flow", failed_recorder)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert Path(receipt["outputs"]["short_mp4"]).exists()
    assert receipt["recording"]["status"] == "failed"
    assert receipt["recording"]["error_code"] == "timeout"
    assert receipt["warnings"] == [
        "app_recording_failed: LIT app did not become ready before timeout"
    ]


def test_unexpected_recorder_exception_is_non_fatal(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        playwright_recording_enabled=True,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)
    monkeypatch.setattr(
        orchestrator_module,
        "record_lit_app_flow",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("browser crashed")),
    )

    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert Path(receipt["outputs"]["short_mp4"]).exists()
    assert receipt["recording"]["status"] == "failed"
    assert receipt["warnings"] == ["app_recording_failed: browser crashed"]


def test_mocked_successful_recorder_writes_receipt_outputs(tmp_path, monkeypatch):
    config = Config(
        mode="mock",
        output_dir=tmp_path / "output",
        playwright_recording_enabled=True,
    )
    orchestrator = _fast_orchestrator(config, monkeypatch)

    def successful_recorder(**kwargs):
        job_dir = kwargs["job_dir"]
        raw = job_dir / "app_recording_raw.webm"
        normalized = job_dir / "app_recording.mp4"
        screenshot = job_dir / "app_recording_final.png"
        raw.write_bytes(b"webm")
        normalized.write_bytes(b"mp4")
        screenshot.write_bytes(b"png")
        return AppRecordingResult(
            success=True,
            raw_video_path=raw,
            normalized_video_path=normalized,
            screenshot_path=screenshot,
            warnings=[],
            metadata={
                "enabled": True,
                "source": "playwright",
                "app_url": kwargs["app_url"],
                "status": "success",
                "raw_video": raw.name,
                "normalized_video": normalized.name,
                "screenshot": screenshot.name,
                "viewport": {
                    "width": kwargs["viewport_width"],
                    "height": kwargs["viewport_height"],
                },
            },
        )

    monkeypatch.setattr(orchestrator_module, "record_lit_app_flow", successful_recorder)
    receipt_path = orchestrator.run_batch(batch=1)[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["recording"]["status"] == "success"
    assert receipt["recording"]["viewport"] == {"width": 1080, "height": 1920}
    expected = {
        "app_recording_raw_webm": "app_recording_raw.webm",
        "app_recording_mp4": "app_recording.mp4",
        "app_recording_final_png": "app_recording_final.png",
    }
    for key, filename in expected.items():
        output = Path(receipt["outputs"][key])
        assert output.name == filename
        assert output.exists()


def test_record_app_cli_flag_is_explicit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orchestrator.py"])
    assert parse_args().record_app is False

    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--record-app"])
    assert parse_args().record_app is True
