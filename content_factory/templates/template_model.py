from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ALLOWED_TEMPLATE_TYPES = frozenset({"script", "caption", "thumbnail", "publisher_metadata", "upload_checklist", "revision", "quality_message"})
ALLOWED_PLACEHOLDERS = frozenset({"idea", "hook", "verdict_headline", "lit_score", "risk_level", "top_reason", "next_step", "source", "locale", "cta", "created_at", "job_id", "platform", "hashtags", "title", "caption", "description", "revision_note", "original_job_id", "quality_score", "quality_status", "recommended_action", "ghost_town_risk", "buyer_pain_clarity", "willingness_to_pay_signal", "distribution_difficulty", "unfair_advantage_check", "business_model_weakness", "why_it_might_work", "why_it_might_fail", "killer_question", "mvp_test"})
FORBIDDEN_PLACEHOLDERS = frozenset({"system", "env", "open_file", "exec", "eval", "import", "__class__"})
TEMPLATE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9][a-z0-9_-]*$")
PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")


def valid_template_id(template_id: object) -> bool:
    return isinstance(template_id, str) and bool(TEMPLATE_ID_PATTERN.fullmatch(template_id))


def template_hash(template: dict[str, Any]) -> str:
    payload = {key: value for key, value in template.items() if key != "template_version_hash"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def content_texts(content: object) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list) and all(isinstance(item, str) for item in content):
        return list(content)
    return []
