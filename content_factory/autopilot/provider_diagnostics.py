from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProviderContentDiagnostics:
    provider_http_status: int | None = None
    provider_selected_model: str | None = None
    provider_selected_provider: str | None = None
    content_present: bool = False
    content_length: int = 0
    content_starts_with_json: bool = False
    content_starts_with_markdown_fence: bool = False
    json_extraction_used: bool = False
    parse_error_type: str | None = None
    compact_schema_valid: bool = False
    internal_schema_valid: bool = False
    missing_required_fields: list[str] = field(default_factory=list)
    schema_error_count: int = 0

    def record_content(self, content: str | None) -> None:
        trimmed = content.strip() if isinstance(content, str) else ""
        self.content_present = bool(trimmed)
        self.content_length = len(trimmed)
        self.content_starts_with_json = trimmed.startswith("{")
        self.content_starts_with_markdown_fence = trimmed.startswith("```")
        if not trimmed:
            self.parse_error_type = "empty_provider_content"

    def record_schema_failure(self, error_type: str, paths: list[str]) -> None:
        self.parse_error_type = error_type
        self.missing_required_fields = sorted(set(paths))
        self.schema_error_count = len(paths)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
