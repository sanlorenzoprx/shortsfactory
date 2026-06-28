from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from content_factory.locales.catalog import labels_for
from content_factory.schemas import LitVerdict
from content_factory.templates import TemplateRenderError, TemplateStore, render_template


class ThumbnailAgent:
    def __init__(self, template_root: str | Path = "templates"):
        self.template_root = template_root
        self.last_template_usage: dict[str, str] | None = None
        self.last_template_warning: str | None = None

    def create_thumbnail(
        self, verdict: LitVerdict, output_path: Path, locale: str = "en-US"
    ) -> Path:
        labels = labels_for(locale)
        text = [labels["thumbnail_title"], verdict.idea.name, f"{verdict.lit_score}/100", verdict.verdict_headline, labels["thumbnail_question"]]
        self.last_template_usage = None
        self.last_template_warning = None
        template = TemplateStore(self.template_root).get("thumbnail.default")
        if template is not None:
            try:
                rendered = render_template(template, {"title": labels["thumbnail_title"], "idea": verdict.idea.name, "lit_score": verdict.lit_score, "verdict_headline": verdict.verdict_headline, "cta": labels["thumbnail_question"], "locale": locale})
                candidate = rendered if isinstance(rendered, list) else rendered.splitlines()
                if len(candidate) < 5:
                    raise TemplateRenderError("thumbnail template must render five text fields")
                text = [str(value) for value in candidate[:5]]
                self.last_template_usage = {"template_id": "thumbnail.default", "template_version_hash": str(template["template_version_hash"]), "source": "local_template"}
            except (TemplateRenderError, KeyError, TypeError, ValueError) as exc:
                self.last_template_warning = f"thumbnail.default template invalid; deterministic fallback used: {exc}"
        else:
            self.last_template_warning = "thumbnail.default template missing or unreadable; deterministic fallback used"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1080, 1920), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        except Exception:
            title_font = body_font = small_font = ImageFont.load_default()

        draw.text((70, 120), text[0], fill=(255, 255, 255), font=title_font, spacing=10)
        y = 470
        for line in wrap(text[1], width=17):
            draw.text((70, y), line, fill=(34, 197, 94), font=body_font)
            y += 86
        draw.rounded_rectangle((70, 1040, 1010, 1300), radius=35, fill=(255, 255, 255))
        draw.text((110, 1080), f"{labels['score']}: {text[2]}", fill=(15, 23, 42), font=body_font)
        draw.text((110, 1180), text[3].upper()[:24], fill=(15, 23, 42), font=small_font)
        draw.text((70, 1680), text[4], fill=(255, 255, 255), font=small_font)
        img.save(output_path, quality=92)
        return output_path
