from __future__ import annotations

import json
import re
import string
from typing import Any

from .template_model import ALLOWED_PLACEHOLDERS, ALLOWED_TEMPLATE_TYPES, FORBIDDEN_PLACEHOLDERS, content_texts, template_hash, valid_template_id

FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _result(template_id: object, errors: list[str], warnings: list[str], found: set[str], value: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "template_id": str(template_id or "unknown"),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "placeholders_found": sorted(found),
        "template_version_hash": template_hash(value) if value is not None and not errors else None,
    }


def validate_template(template: object) -> dict[str, Any]:
    if not isinstance(template, dict):
        return _result("unknown", ["Template must be a JSON object."], [], set())
    errors: list[str] = []
    warnings: list[str] = []
    found: set[str] = set()
    template_id = template.get("template_id")
    template_type = template.get("template_type")
    if not valid_template_id(template_id):
        errors.append("template_id must be a safe type.name identifier.")
    if template_type not in ALLOWED_TEMPLATE_TYPES:
        errors.append("template_type is not allowed.")
    elif isinstance(template_id, str) and template_id.split(".", 1)[0] != template_type:
        errors.append("template_id prefix must match template_type.")
    texts = content_texts(template.get("content"))
    if not texts or (len(texts) == 1 and not texts[0]):
        errors.append("content must be a non-empty string or list of strings.")
    required = template.get("required_placeholders")
    optional = template.get("optional_placeholders", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        errors.append("required_placeholders must be a list of names.")
        required = []
    if not isinstance(optional, list) or not all(isinstance(item, str) for item in optional):
        errors.append("optional_placeholders must be a list of names.")
        optional = []
    declared = set(required) | set(optional)
    forbidden_declared = declared & FORBIDDEN_PLACEHOLDERS
    if forbidden_declared:
        errors.append("Forbidden placeholders declared: " + ", ".join(sorted(forbidden_declared)) + ".")
    unknown_declared = declared - ALLOWED_PLACEHOLDERS
    if unknown_declared:
        errors.append("Unknown placeholders declared: " + ", ".join(sorted(unknown_declared)) + ".")
    formatter = string.Formatter()
    for text in texts:
        try:
            for _, field_name, format_spec, conversion in formatter.parse(text):
                if field_name is None:
                    continue
                if not FIELD_NAME.fullmatch(field_name):
                    errors.append(f"Suspicious placeholder syntax: {{{field_name}}}.")
                    continue
                found.add(field_name)
                if conversion or format_spec:
                    errors.append(f"Placeholder expressions are not supported: {{{field_name}}}.")
        except ValueError as exc:
            errors.append(f"Invalid placeholder braces: {exc}.")
    forbidden_found = found & FORBIDDEN_PLACEHOLDERS
    if forbidden_found:
        errors.append("Forbidden placeholders found: " + ", ".join(sorted(forbidden_found)) + ".")
    unknown_found = found - ALLOWED_PLACEHOLDERS
    if unknown_found:
        errors.append("Unknown placeholders found: " + ", ".join(sorted(unknown_found)) + ".")
    missing_required = set(required) - found
    if missing_required:
        errors.append("Required placeholders missing from content: " + ", ".join(sorted(missing_required)) + ".")
    undeclared = found - declared
    if undeclared:
        errors.append("Placeholders must be declared: " + ", ".join(sorted(undeclared)) + ".")
    if not isinstance(template.get("enabled"), bool):
        errors.append("enabled must be boolean.")
    if not isinstance(template.get("locked"), bool):
        errors.append("locked must be boolean.")
    version = template.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("version must be a positive integer.")
    max_lines = template.get("max_lines")
    max_chars = template.get("max_chars_per_line")
    if not isinstance(max_lines, int) or isinstance(max_lines, bool) or not 1 <= max_lines <= 1000:
        errors.append("max_lines must be an integer from 1 to 1000.")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 1 <= max_chars <= 10000:
        errors.append("max_chars_per_line must be an integer from 1 to 10000.")
    line_count = sum(max(1, len(text.splitlines())) for text in texts)
    if isinstance(max_lines, int) and line_count > max_lines:
        warnings.append(f"Content has {line_count} lines, above max_lines {max_lines}.")
    if isinstance(max_chars, int):
        longest = max((len(line) for text in texts for line in (text.splitlines() or [text])), default=0)
        if longest > max_chars:
            warnings.append(f"Content has a {longest}-character line, above max_chars_per_line {max_chars}.")
    return _result(template_id, errors, warnings, found, template)


def validate_template_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        return _result("unknown", [f"Invalid JSON: {exc}."], [], set())
    return validate_template(value)
