from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from content_factory.locales.catalog import labels_for
from content_factory.schemas import LitVerdict


class ThumbnailAgent:
    def create_thumbnail(
        self, verdict: LitVerdict, output_path: Path, locale: str = "en-US"
    ) -> Path:
        labels = labels_for(locale)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1080, 1920), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        except Exception:
            title_font = body_font = small_font = ImageFont.load_default()

        draw.text((70, 120), labels["thumbnail_title"], fill=(255, 255, 255), font=title_font, spacing=10)
        y = 470
        for line in wrap(verdict.idea.name, width=17):
            draw.text((70, y), line, fill=(34, 197, 94), font=body_font)
            y += 86
        draw.rounded_rectangle((70, 1040, 1010, 1300), radius=35, fill=(255, 255, 255))
        draw.text((110, 1080), f"{labels['score']}: {verdict.lit_score}/100", fill=(15, 23, 42), font=body_font)
        draw.text((110, 1180), verdict.verdict_headline.upper()[:24], fill=(15, 23, 42), font=small_font)
        draw.text((70, 1680), labels["thumbnail_question"], fill=(255, 255, 255), font=small_font)
        img.save(output_path, quality=92)
        return output_path
