from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import TemplateRegistry
from .template_model import template_hash, valid_template_id
from .template_validator import validate_template


class TemplateStoreError(ValueError):
    """Safe local-template storage error."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemplateStore:
    def __init__(self, template_root: str | Path = "templates"):
        self.registry = TemplateRegistry(template_root)
        self.root = self.registry.root

    def list(self) -> list[dict[str, Any]]:
        return self.registry.list()

    def get(self, template_id: str) -> dict[str, Any] | None:
        try:
            return self.registry.get(template_id)
        except ValueError as exc:
            raise TemplateStoreError(str(exc)) from exc

    def validate(self, template_id: str) -> dict[str, Any]:
        value = self.get(template_id)
        if value is None:
            raise TemplateStoreError(f"template not found: {template_id}")
        return validate_template(value)

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _history_dir(self, template_id: str) -> Path:
        if not valid_template_id(template_id):
            raise TemplateStoreError("invalid template_id")
        path = (self.root / "history" / template_id).resolve()
        if self.root != path and self.root not in path.parents:
            raise TemplateStoreError("history path escapes template root")
        return path

    def history(self, template_id: str) -> list[dict[str, str]]:
        directory = self._history_dir(template_id)
        if not directory.is_dir():
            return []
        return [{"history_id": path.name, "path": str(path)} for path in sorted(directory.glob("*.json"), reverse=True)]

    def save(self, template_id: str, template: dict[str, Any]) -> dict[str, Any]:
        current = self.get(template_id)
        if current is None:
            raise TemplateStoreError(f"template not found: {template_id}")
        if current.get("locked") is True:
            raise TemplateStoreError("locked templates cannot be overwritten")
        if not isinstance(template, dict) or template.get("template_id") != template_id:
            raise TemplateStoreError("template_id cannot be changed while saving")
        now = utc_now_iso()
        candidate = dict(template)
        candidate["version"] = int(current.get("version", 0)) + 1
        candidate["created_at"] = current.get("created_at") or now
        candidate["updated_at"] = now
        candidate["template_version_hash"] = template_hash(candidate)
        validation = validate_template(candidate)
        if not validation["valid"]:
            raise TemplateStoreError("Invalid template: " + "; ".join(validation["errors"]))
        stamp = now.replace(":", "-").replace("+", "_")
        prior_hash = str(current.get("template_version_hash") or template_hash(current)).replace("sha256:", "")[:12]
        self._atomic_write(self._history_dir(template_id) / f"{stamp}_{prior_hash}.json", current)
        self._atomic_write(self.registry.local_path(template_id), candidate)
        return candidate

    def restore(self, template_id: str, history_id: str) -> dict[str, Any]:
        if not history_id or Path(history_id).name != history_id or not history_id.endswith(".json"):
            raise TemplateStoreError("invalid history revision")
        history_dir = self._history_dir(template_id)
        path = (history_dir / history_id).resolve()
        if path.parent != history_dir or not path.is_file():
            raise TemplateStoreError("history revision not found")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TemplateStoreError("history revision is invalid JSON") from exc
        validation = validate_template(value)
        if not validation["valid"]:
            raise TemplateStoreError("History revision is invalid: " + "; ".join(validation["errors"]))
        return self.save(template_id, value)
