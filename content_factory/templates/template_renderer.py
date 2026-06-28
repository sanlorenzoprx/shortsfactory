from __future__ import annotations

import re
from typing import Any

from .template_model import PLACEHOLDER_PATTERN
from .template_validator import validate_template


class TemplateRenderError(ValueError):
    """Raised when a text template cannot be rendered safely."""


def _render_text(value: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in context or context[name] is None:
            raise TemplateRenderError(f"Missing context value for placeholder: {name}")
        replacement = context[name]
        if isinstance(replacement, (list, tuple)):
            return " ".join(str(item) for item in replacement)
        if isinstance(replacement, (dict, set)):
            raise TemplateRenderError(f"Context value must be plain text: {name}")
        return str(replacement)
    return PLACEHOLDER_PATTERN.sub(replace, value)


def render_template(template: dict[str, Any], context: dict[str, Any]) -> str | list[str]:
    result = validate_template(template)
    if not result["valid"]:
        raise TemplateRenderError("Invalid template: " + "; ".join(result["errors"]))
    if not template.get("enabled", False):
        raise TemplateRenderError("Template is disabled.")
    content = template["content"]
    if isinstance(content, str):
        return _render_text(content, context)
    return [_render_text(line, context) for line in content]
