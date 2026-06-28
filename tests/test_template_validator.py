import json

from content_factory.templates.default_templates import builtin_templates
from content_factory.templates.template_validator import validate_template, validate_template_json


def test_valid_template_has_deterministic_hash():
    template = builtin_templates()["script.default"]
    first = validate_template(template)
    second = validate_template(template)
    assert first["valid"] is True
    assert first["template_version_hash"] == second["template_version_hash"]


def test_invalid_json_fails_safely():
    result = validate_template_json("{definitely not json")
    assert result["valid"] is False
    assert "Invalid JSON" in result["errors"][0]


def test_unknown_and_forbidden_placeholders_are_rejected():
    template = builtin_templates()["script.default"]
    template["content"].append("{system} {mystery}")
    template["optional_placeholders"].extend(["system", "mystery"])
    result = validate_template(template)
    assert result["valid"] is False
    assert any("Forbidden" in error for error in result["errors"])
    assert any("Unknown" in error for error in result["errors"])


def test_missing_required_placeholder_is_rejected():
    template = builtin_templates()["script.default"]
    template["content"] = [line for line in template["content"] if "{cta}" not in line]
    result = validate_template(template)
    assert result["valid"] is False
    assert any("cta" in error and "missing" in error for error in result["errors"])


def test_expression_syntax_is_rejected():
    template = builtin_templates()["script.default"]
    template["content"].append("{idea.__class__}")
    result = validate_template(template)
    assert result["valid"] is False
    assert any("Suspicious" in error for error in result["errors"])
