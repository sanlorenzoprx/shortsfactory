from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JSONExtractionDiagnostics:
    json_extraction_used: bool
    parse_error_type: str | None
    json_parse_error_type: str | None = None
    json_parse_error_line: int | None = None
    json_parse_error_column: int | None = None
    json_parse_error_position: int | None = None
    extracted_json_length: int = 0
    extracted_json_starts_with_object: bool = False
    extracted_json_ends_with_object: bool = False
    brace_balance_delta: int = 0
    bracket_balance_delta: int = 0
    quote_count_parity_even: bool = True
    contains_control_characters: bool = False
    likely_truncated: bool = False
    multiple_json_objects_detected: bool = False
    trailing_text_after_json_detected: bool = False
    markdown_fence_detected: bool = False
    parse_stage: str | None = None


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


def _first_complete_object_end(value: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(value)):
        character = value[index]
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
                return index + 1
    return None


def _structural_metadata(value: str) -> tuple[int, int, int, bool]:
    braces = 0
    brackets = 0
    quotes = 0
    in_string = False
    escaped = False
    trailing_comma = False
    for index, character in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
                quotes += 1
            continue
        if character == '"':
            in_string = True
            quotes += 1
        elif character == "{":
            braces += 1
        elif character == "}":
            braces -= 1
        elif character == "[":
            brackets += 1
        elif character == "]":
            brackets -= 1
        elif character == ",":
            remainder = value[index + 1:].lstrip()
            trailing_comma = trailing_comma or remainder.startswith(("}", "]"))
    return braces, brackets, quotes, trailing_comma


def _contains_complete_json_object(value: str) -> bool:
    offset = 0
    while True:
        start = value.find("{", offset)
        if start < 0:
            return False
        end = _first_complete_object_end(value, start)
        if end is None:
            return False
        try:
            candidate = json.loads(value[start:end])
        except json.JSONDecodeError:
            offset = start + 1
            continue
        if isinstance(candidate, dict):
            return True
        offset = end


def _safe_json_error_type(error: json.JSONDecodeError, *, trailing_comma: bool, likely_truncated: bool) -> str:
    if trailing_comma:
        return "trailing_comma"
    if likely_truncated:
        return "unexpected_end_of_json"
    message = error.msg.casefold()
    known = (
        ("unterminated string", "unterminated_string"),
        ("invalid control character", "invalid_control_character"),
        ("expecting property name enclosed in double quotes", "property_name_not_double_quoted"),
        ("expecting ',' delimiter", "missing_comma_delimiter"),
        ("expecting ':' delimiter", "missing_colon_delimiter"),
        ("extra data", "extra_data"),
        ("invalid \\escape", "invalid_escape"),
        ("expecting value", "expecting_value"),
    )
    for prefix, safe_type in known:
        if message.startswith(prefix):
            return safe_type
    return "json_decode_error"


def _diagnostics_for_candidate(
    candidate: str,
    *,
    extraction_used: bool,
    trailing: str,
    markdown_fence_detected: bool,
    parse_error: json.JSONDecodeError | None = None,
    parse_error_type: str | None = None,
) -> JSONExtractionDiagnostics:
    braces, brackets, quotes, trailing_comma = _structural_metadata(candidate)
    likely_truncated = (
        candidate.lstrip().startswith("{")
        and (braces > 0 or brackets > 0 or quotes % 2 != 0 or not candidate.rstrip().endswith("}"))
    )
    safe_error_type = parse_error_type
    if parse_error is not None:
        safe_error_type = _safe_json_error_type(
            parse_error,
            trailing_comma=trailing_comma,
            likely_truncated=likely_truncated,
        )
    return JSONExtractionDiagnostics(
        json_extraction_used=extraction_used,
        parse_error_type="malformed_json" if safe_error_type else None,
        json_parse_error_type=safe_error_type,
        json_parse_error_line=parse_error.lineno if parse_error is not None else None,
        json_parse_error_column=parse_error.colno if parse_error is not None else None,
        json_parse_error_position=parse_error.pos if parse_error is not None else None,
        extracted_json_length=len(candidate),
        extracted_json_starts_with_object=candidate.lstrip().startswith("{"),
        extracted_json_ends_with_object=candidate.rstrip().endswith("}"),
        brace_balance_delta=braces,
        bracket_balance_delta=brackets,
        quote_count_parity_even=quotes % 2 == 0,
        contains_control_characters=bool(re.search(r"[\x00-\x1f\x7f]", candidate)),
        likely_truncated=likely_truncated,
        multiple_json_objects_detected=_contains_complete_json_object(trailing),
        trailing_text_after_json_detected=bool(trailing.strip()),
        markdown_fence_detected=markdown_fence_detected,
        parse_stage="json_loads",
    )


def extract_first_complete_json_object(
    content: str,
) -> tuple[dict[str, Any] | None, JSONExtractionDiagnostics]:
    trimmed = content.strip() if isinstance(content, str) else ""
    if not trimmed:
        return None, JSONExtractionDiagnostics(
            False,
            "empty_provider_content",
            parse_stage="content_extraction",
        )

    markdown_fence_detected = "```" in trimmed
    if not trimmed.startswith("{"):
        try:
            direct = json.loads(trimmed)
        except json.JSONDecodeError:
            direct = None
        else:
            if not isinstance(direct, dict):
                diagnostics = _diagnostics_for_candidate(
                    trimmed,
                    extraction_used=False,
                    trailing="",
                    markdown_fence_detected=markdown_fence_detected,
                    parse_error_type="top_level_not_object",
                )
                return None, diagnostics

    start = trimmed.find("{")
    if start < 0:
        return None, JSONExtractionDiagnostics(
            False,
            "malformed_json",
            json_parse_error_type="extraction_failed",
            markdown_fence_detected=markdown_fence_detected,
            parse_stage="json_extraction",
        )

    end = _first_complete_object_end(trimmed, start)
    candidate = trimmed[start:end] if end is not None else trimmed[start:]
    trailing = trimmed[end:] if end is not None else ""
    extraction_used = start != 0 or (end is not None and end != len(trimmed))
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, _diagnostics_for_candidate(
            candidate,
            extraction_used=extraction_used,
            trailing=trailing,
            markdown_fence_detected=markdown_fence_detected,
            parse_error=exc,
        )
    if not isinstance(value, dict):
        return None, _diagnostics_for_candidate(
            candidate,
            extraction_used=extraction_used,
            trailing=trailing,
            markdown_fence_detected=markdown_fence_detected,
            parse_error_type="top_level_not_object",
        )
    return value, _diagnostics_for_candidate(
        candidate,
        extraction_used=extraction_used,
        trailing=trailing,
        markdown_fence_detected=markdown_fence_detected,
    )
