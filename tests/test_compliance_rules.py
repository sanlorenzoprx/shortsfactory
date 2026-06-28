from content_factory.compliance.compliance_rules import (
    platform_copy_warnings,
    text_warning_checks,
)


def test_text_warning_checks_detect_placeholder_text():
    warnings = text_warning_checks("title", "TODO finish <title> {hook}")
    messages = [item["message"] for item in warnings]
    assert any("TODO" in message or "todo" in message.casefold() for message in messages)
    assert any("<title>" in message for message in messages)
    assert any("{hook}" in message for message in messages)


def test_text_warning_checks_detect_risky_phrases():
    warnings = text_warning_checks("caption", "Guaranteed instant results with no effort.")
    codes = {item["code"] for item in warnings}
    assert "caption_risky_phrase" in codes


def test_youtube_platform_warning_detects_missing_shorts_hashtag():
    warnings = platform_copy_warnings(
        "youtube_shorts",
        title="A safe title",
        description="A safe description",
        hashtags=("#startup",),
    )
    codes = {item["code"] for item in warnings}
    assert "youtube_missing_shorts_hashtag" in codes
