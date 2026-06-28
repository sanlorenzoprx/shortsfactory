from content_factory.previews.platform_rules import platform_warnings


def codes(platform: str, **values) -> set[str]:
    return {item["code"] for item in platform_warnings(platform, **values)}


def test_youtube_missing_shorts_hashtag_is_advisory():
    warnings = platform_warnings("youtube_shorts", title="Title", description="Description", hashtags=("#startup",))
    assert "missing_shorts_hashtag" in {item["code"] for item in warnings}
    assert all(item["type"] == "local_advisory_warning" for item in warnings)


def test_tiktok_missing_hashtag_is_advisory():
    assert "missing_hashtags" in codes("tiktok", caption="Caption", hashtags=())


def test_instagram_too_many_hashtags_is_advisory():
    hashtags = tuple(f"#tag{index}" for index in range(31))
    assert "too_many_hashtags" in codes("instagram_reels", caption="Caption", hashtags=hashtags)
