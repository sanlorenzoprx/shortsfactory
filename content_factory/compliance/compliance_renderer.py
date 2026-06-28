from __future__ import annotations

from typing import Any

from .compliance_models import STATUS_NEEDS_REVIEW, STATUS_READY


def status_label(status: str) -> str:
    if status == STATUS_READY:
        return "Ready for Manual Upload"
    if status == STATUS_NEEDS_REVIEW:
        return "Needs Human Review"
    return status.replace("_", " ").title()


def machine_status(checklist: dict[str, Any]) -> str:
    statuses = {
        str(item.get("status", ""))
        for item in checklist.get("checks", [])
        if isinstance(item, dict)
    }
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def human_status(checklist: dict[str, Any]) -> str:
    items = [
        item for item in checklist.get("human_review_items", []) if isinstance(item, dict)
    ]
    if items and all(bool(item.get("checked")) for item in items if item.get("required", True)):
        return "complete"
    return "incomplete"


def render_markdown(checklist: dict[str, Any]) -> str:
    required_lines: list[str] = []
    advisory_lines: list[str] = []
    for item in checklist.get("checks", []):
        if not isinstance(item, dict):
            continue
        mark = "x" if item.get("status") == "pass" else " "
        line = f"- [{mark}] {item.get('label', 'Unnamed check')}"
        if item.get("severity") == "required":
            required_lines.append(line)
        elif item.get("status") == "warn":
            advisory_lines.append(f"- [!] {item.get('label', 'Unnamed warning')}")
    human_lines = [
        f"- [{'x' if item.get('checked') else ' '}] {item.get('label', 'Unnamed review item')}"
        for item in checklist.get("human_review_items", [])
        if isinstance(item, dict)
    ]
    warnings = checklist.get("warnings", [])
    warning_lines = []
    for entry in warnings:
        if isinstance(entry, dict):
            warning_lines.append(f"- {entry.get('message', 'Warning')}")
        else:
            warning_lines.append(f"- {entry}")
    errors = checklist.get("errors", [])
    error_lines = []
    for entry in errors:
        if isinstance(entry, dict):
            error_lines.append(f"- {entry.get('message', 'Error')}")
        else:
            error_lines.append(f"- {entry}")
    reviewed_block = ""
    if checklist.get("ready_for_manual_upload") is True:
        reviewed_block = (
            "\n## Review Confirmation\n\n"
            f"- Reviewed at: {checklist.get('reviewed_at', 'unknown')}\n"
            f"- Review method: {checklist.get('review_method', 'unknown')}\n"
        )
    return (
        "# Final Manual Upload Compliance Checklist\n\n"
        "## Status\n\n"
        f"{status_label(str(checklist.get('status', 'needs_human_review')))}\n\n"
        "## Required Artifact Checks\n\n"
        + ("\n".join(required_lines) if required_lines else "- [ ] No required checks recorded")
        + "\n\n## Human Review Required\n\n"
        + ("\n".join(human_lines) if human_lines else "- [ ] No human review items recorded")
        + "\n\n## Advisory Warnings\n\n"
        + ("\n".join(advisory_lines + warning_lines) if advisory_lines or warning_lines else "- None")
        + "\n\n## Errors\n\n"
        + ("\n".join(error_lines) if error_lines else "- None")
        + reviewed_block
        + "\n## Safety Boundary\n\n"
        + "Shorts Factory has not published this video.\n"
        + "No platform API upload was attempted.\n"
        + "Manual upload only.\n"
    )
