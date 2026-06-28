from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .default_templates import builtin_templates
from .template_model import valid_template_id
from .template_validator import validate_template


class TemplateRegistry:
    def __init__(self, template_root: str | Path = "templates"):
        self.root = Path(template_root).expanduser().resolve()

    def local_path(self, template_id: str) -> Path:
        if not valid_template_id(template_id):
            raise ValueError("invalid template_id")
        template_type, name = template_id.split(".", 1)
        path = (self.root / template_type / f"{name}.json").resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("template path escapes template root")
        return path

    def _local_templates(self) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        if not self.root.is_dir():
            return values
        for path in sorted(self.root.glob("*/*.json")):
            resolved = path.resolve()
            if self.root != resolved and self.root not in resolved.parents:
                continue
            try:
                value = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            template_id = value.get("template_id")
            if valid_template_id(template_id) and resolved == self.local_path(template_id):
                values[template_id] = value
        return values

    def list(self) -> list[dict[str, Any]]:
        local = self._local_templates()
        merged = builtin_templates()
        merged.update(local)
        return [
            {
                **merged[template_id],
                "source": "local" if template_id in local else "built_in",
                "validation": validate_template(merged[template_id]),
            }
            for template_id in sorted(merged)
        ]

    def get(self, template_id: str) -> dict[str, Any] | None:
        path = self.local_path(template_id)
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None
        return builtin_templates().get(template_id)
