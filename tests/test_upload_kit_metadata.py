from content_factory.upload_kits.checklist_builder import build_checklist
from content_factory.upload_kits.metadata_formatter import format_platform_copy
from content_factory.upload_kits.platform_profiles import PLATFORM_PROFILES


def sources():
    receipt = {
        "idea": {"name": "Builder Test"},
        "verdict": {
            "verdict_headline": "A very long builder verdict " * 8,
            "top_reason": "Clear idea-validation signal.",
        },
    }
    script = "Test this Ghost Town idea before building.\nScore: 80.\nTry it now."
    return receipt, script


def test_youtube_title_and_platform_hashtags_are_capped():
    receipt, script = sources()
    for key, cap in (("youtube_shorts", 8), ("tiktok", 6), ("instagram_reels", 10)):
        formatted = format_platform_copy(PLATFORM_PROFILES[key], receipt, script, {})
        assert len(formatted["hashtags"]) <= cap
        assert len(set(formatted["hashtags"])) == len(formatted["hashtags"])
    youtube = format_platform_copy(PLATFORM_PROFILES["youtube_shorts"], receipt, script, {})
    assert len(youtube["title"]) <= 80
    assert "#shorts" in youtube["hashtags"]


def test_publisher_caption_has_priority_when_available():
    receipt, script = sources()
    package = {"platforms": {"tiktok": {"caption": "Publisher caption wins."}}}

    formatted = format_platform_copy(PLATFORM_PROFILES["tiktok"], receipt, script, package)

    assert formatted["caption"] == "Publisher caption wins."


def test_all_checklists_are_manual_and_not_published():
    for platform in PLATFORM_PROFILES:
        checklist = build_checklist(platform)
        assert "Manual Upload Checklist" in checklist
        assert "Publish manually only after final human review." in checklist
        assert "DRY RUN ONLY - NOT PUBLISHED BY SHORTS FACTORY" in checklist
