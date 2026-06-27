from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AppRecordingResult:
    success: bool
    raw_video_path: Path | None
    normalized_video_path: Path | None
    screenshot_path: Path | None
    warnings: list[str]
    metadata: dict[str, Any]


def record_lit_app_flow(
    *,
    app_url: str,
    idea: str,
    verdict: dict[str, Any],
    job_dir: Path,
    locale: str,
    headless: bool,
    timeout_ms: int,
    viewport_width: int = 1080,
    viewport_height: int = 1920,
) -> AppRecordingResult:
    """Record the controlled, synthetic LIT demo flow.

    The verdict request is fulfilled from the verdict already produced for this
    Shorts Factory job. This keeps the browser flow deterministic and prevents
    the recording step from submitting synthetic data to another service.
    """

    job_dir.mkdir(parents=True, exist_ok=True)
    app_url = app_url.strip()
    raw_path = job_dir / "app_recording_raw.webm"
    normalized_path = job_dir / "app_recording.mp4"
    screenshot_path = job_dir / "app_recording_final.png"
    video_dir = job_dir / ".playwright-video"
    metadata = _recording_metadata(
        app_url=app_url,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        locale=locale,
    )

    context = None
    browser = None
    video = None
    try:
        if not app_url:
            raise ValueError("LIT_APP_URL is blank")

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed; run pip install -r requirements.txt"
            ) from exc

        video_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                record_video_dir=str(video_dir),
                record_video_size={"width": viewport_width, "height": viewport_height},
                locale=locale,
            )
            page = context.new_page()
            video = page.video
            page.set_default_timeout(timeout_ms)
            page.route("**/api/verdict", lambda route: _fulfill_demo_verdict(route, verdict))

            page.goto(app_url, wait_until="domcontentloaded", timeout=timeout_ms)
            _open_idea_intake(page)
            _fill_synthetic_idea(page, idea, verdict)
            page.get_by_test_id("evaluate-button").click()
            _answer_controlled_questions(page, timeout_ms, PlaywrightTimeoutError)
            page.get_by_test_id("verdict-card").wait_for(state="visible", timeout=timeout_ms)
            page.screenshot(path=str(screenshot_path), full_page=True)

            context.close()
            context = None
            recorded_path = Path(video.path())
            browser.close()
            browser = None

        shutil.move(str(recorded_path), raw_path)
        _normalize_video(raw_path, normalized_path, viewport_width, viewport_height)
        metadata.update(
            {
                "status": "success",
                "raw_video": raw_path.name,
                "normalized_video": normalized_path.name,
                "screenshot": screenshot_path.name,
            }
        )
        return AppRecordingResult(
            success=True,
            raw_video_path=raw_path,
            normalized_video_path=normalized_path,
            screenshot_path=screenshot_path,
            warnings=[],
            metadata=metadata,
        )
    except Exception as exc:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if video is not None and not raw_path.exists():
            try:
                candidate = Path(video.path())
                if candidate.exists():
                    shutil.move(str(candidate), raw_path)
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        error_code = _error_code(exc)
        details = " ".join(str(exc).split()) or type(exc).__name__
        warning = f"app_recording_failed: {details[:300]}"
        metadata.update({"status": "failed", "error_code": error_code})
        return AppRecordingResult(
            success=False,
            raw_video_path=raw_path if raw_path.exists() else None,
            normalized_video_path=normalized_path if normalized_path.exists() else None,
            screenshot_path=screenshot_path if screenshot_path.exists() else None,
            warnings=[warning],
            metadata=metadata,
        )
    finally:
        shutil.rmtree(video_dir, ignore_errors=True)


def _recording_metadata(
    *, app_url: str, viewport_width: int, viewport_height: int, locale: str
) -> dict[str, Any]:
    return {
        "enabled": True,
        "source": "playwright",
        "app_url": app_url,
        "status": "started",
        "viewport": {"width": viewport_width, "height": viewport_height},
        "locale": locale,
        "flow": "controlled_synthetic_demo",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _open_idea_intake(page: Any) -> None:
    idea_input = page.get_by_test_id("idea-input")
    if idea_input.count() and idea_input.first.is_visible():
        return

    start_button = page.get_by_role(
        "button", name=re.compile(r"validate (your|my) idea free|start", re.IGNORECASE)
    ).first
    start_button.click()
    idea_input.wait_for(state="visible")


def _fill_synthetic_idea(page: Any, idea: str, verdict: dict[str, Any]) -> None:
    idea_data = verdict.get("idea") if isinstance(verdict.get("idea"), dict) else {}
    description = str(idea_data.get("description") or f"A controlled demo of {idea}.")
    target_user = str(idea_data.get("target_user") or "early-stage builders")

    page.get_by_test_id("idea-input").fill(idea[:120])
    page.locator('form textarea[name="description"]').fill(description[:600])
    page.locator('form input[name="targetUser"]').fill(target_user[:200])
    page.locator('form textarea[name="painfulProblem"]').fill(
        "Teams lose time and money when they build before validating demand."
    )
    page.locator('form input[name="currentAlternative"]').fill(
        "Manual interviews and disconnected validation notes."
    )
    page.locator('form textarea[name="motivation"]').fill(
        "Validate a synthetic seed idea in a controlled product demo."
    )


def _answer_controlled_questions(
    page: Any, timeout_ms: int, playwright_timeout_error: type[Exception]
) -> None:
    deadline_ms = timeout_ms
    elapsed_ms = 0
    answer_delay_ms = 180

    while elapsed_ms < deadline_ms:
        verdict_card = page.get_by_test_id("verdict-card")
        if verdict_card.count() and verdict_card.first.is_visible():
            return

        options = page.locator('main button[aria-pressed]')
        if options.count():
            # The fourth response provides a consistent, credible demo verdict.
            options.nth(min(3, options.count() - 1)).click()
            page.wait_for_timeout(answer_delay_ms)
            elapsed_ms += answer_delay_ms
            continue

        page.wait_for_timeout(100)
        elapsed_ms += 100

    raise playwright_timeout_error("LIT app did not become ready before timeout")


def _fulfill_demo_verdict(route: Any, verdict: dict[str, Any]) -> None:
    score_100 = _bounded_number(verdict.get("lit_score"), 70, 0, 100)
    score_5 = round(score_100 / 20, 1)
    risk = str(verdict.get("risk_level") or "medium")
    headline = str(verdict.get("verdict_headline") or "Test this idea first")
    next_step = str(verdict.get("next_step") or "Run a small demand test.")
    top_reason = str(verdict.get("top_reason") or "Demand needs direct evidence.")
    idea_data = verdict.get("idea") if isinstance(verdict.get("idea"), dict) else {}

    payload = {
        "idea": {
            "ideaName": str(idea_data.get("name") or "Synthetic demo idea"),
            "description": str(idea_data.get("description") or "Controlled demo input"),
            "targetUser": str(idea_data.get("target_user") or "early-stage builders"),
            "painfulProblem": "Building before demand is validated",
            "currentAlternative": "Manual validation",
            "motivation": "Controlled product demo",
        },
        "answers": {},
        "deterministicScores": {
            "ghostTownScore": score_5,
            "ghostTownRisk": risk,
            "leverageScore": score_5,
            "insightScore": score_5,
            "timingScore": score_5,
            "litScore": score_5,
            "litBand": "promising" if score_5 >= 3 else "unclear",
            "passionRiskScore": 3.5,
            "businessDnaType": "expert",
            "businessDnaTrap": top_reason,
            "businessDnaWinStrategy": next_step,
            "highWallsScore": 3.0,
            "highWallsBand": "unclear",
            "finalVerdict": "test_first",
            "verdictHeadline": headline,
            "oneSentenceAdvice": top_reason,
            "doNotBuildUntil": top_reason,
            "recommendedNextTest": next_step,
        },
        "verdict": {
            "verdict": "test_first",
            "verdict_headline": headline,
            "one_sentence_advice": top_reason,
            "do_not_build_until": top_reason,
            "recommended_next_test": next_step,
            "biggest_trap": top_reason,
        },
        "usedAI": False,
        "cacheHit": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _bounded_number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_video(raw_path: Path, output_path: Path, width: int, height: int) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("ffmpeg is required to normalize app_recording.mp4")

    executable = str(Path(executable).resolve())
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    command = [
        executable,
        "-y",
        "-i",
        str(raw_path),
        "-vf",
        video_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg could not normalize app recording: {details}") from exc


def _error_code(exc: Exception) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in text:
        return "timeout"
    if "playwright is not installed" in text:
        return "playwright_unavailable"
    if "executable doesn't exist" in text or "browser" in text or "chromium" in text:
        return "browser_unavailable"
    if "ffmpeg" in text:
        return "ffmpeg"
    if "selector" in text or "locator" in text or "testid" in text:
        return "selector"
    return "recording_error"
