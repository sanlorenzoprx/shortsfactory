from pathlib import Path

from content_factory.previews import generate_preview_cards
from tests.test_preview_cards import create_preview_sources


def test_preview_html_escapes_user_controlled_script_tags(tmp_path: Path):
    export_root = tmp_path / "exports"
    _, kit = create_preview_sources(export_root)
    unsafe = "<script>alert('preview')</script>"
    (kit / "youtube_shorts" / "title.txt").write_text(unsafe, encoding="utf-8")
    (kit / "youtube_shorts" / "upload_checklist.md").write_text(f"- [ ] {unsafe}", encoding="utf-8")

    result = generate_preview_cards("approved-job", export_root)
    html = (result.preview_dir / "youtube_shorts_preview.html").read_text(encoding="utf-8")

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "<script src=" not in html
    assert "https://" not in html
