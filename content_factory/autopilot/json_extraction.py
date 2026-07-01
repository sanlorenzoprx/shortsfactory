from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JSONExtractionDiagnostics:
    json_extraction_used: bool
    parse_error_type: str | None


def _value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def extract_openrouter_message_content(response: Any) -> str | None:
    choices = _value(response, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    message = _value(choices[0], "message")
    content = _value(message, "content")
    return content if isinstance(content, str) else None


def extract_response_value(response: Any, key: str) -> Any:
    return _value(response, key)


def extract_first_complete_json_object(
    content: str,
) -> tuple[dict[str, Any] | None, JSONExtractionDiagnostics]:
    trimmed = content.strip() if isinstance(content, str) else ""
    if not trimmed:
        return None, JSONExtractionDiagnostics(False, "empty_provider_content")

    sentinel = object()
    try:
        direct: Any = json.loads(trimmed)
    except json.JSONDecodeError:
        direct = sentinel
    if isinstance(direct, dict):
        return direct, JSONExtractionDiagnostics(False, None)
    if direct is not sentinel:
        return None, JSONExtractionDiagnostics(False, "malformed_json")

    start = trimmed.find("{")
    if start < 0:
        return None, JSONExtractionDiagnostics(False, "json_object_not_found")

    depth = 0
    in_string = False
    escaped = False
    end: int | None = None
    for index in range(start, len(trimmed)):
        character = trimmed[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        return None, JSONExtractionDiagnostics(True, "malformed_json")
    candidate = trimmed[start:end]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None, JSONExtractionDiagnostics(True, "malformed_json")
    if not isinstance(value, dict):
        return None, JSONExtractionDiagnostics(True, "malformed_json")
    return value, JSONExtractionDiagnostics(start != 0 or end != len(trimmed), None)
