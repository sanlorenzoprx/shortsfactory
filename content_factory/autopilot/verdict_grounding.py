from __future__ import annotations

import re
from collections import Counter
from typing import Any


GROUNDING_PACKET_FIELDS = (
    "idea_label",
    "idea_summary",
    "verdict_label",
    "verdict_summary",
    "target_buyer_terms",
    "problem_terms",
    "pain_terms",
    "risk_terms",
    "validation_action_terms",
    "opportunity_terms",
    "verdict_signal_terms",
    "forbidden_external_fact_categories",
)
EXTERNAL_FACT_CATEGORIES = (
    "unsupported_market_claim",
    "unsupported_buyer_claim",
    "unsupported_metric_claim",
    "unsupported_revenue_claim",
    "unsupported_platform_claim",
    "unsupported_timing_claim",
    "unsupported_competitor_claim",
    "unsupported_guarantee_claim",
    "unsupported_outcome_claim",
    "unknown_entity_signal",
)
PROJECT_TERMS = {
    "ghost", "town", "test", "ghosttowntest", "lit", "verdict", "builder",
    "buyer", "validation", "idea", "market", "mvp", "risk", "demand", "signal",
}
TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
STOPWORDS = {
    "and", "are", "but", "for", "from", "has", "have", "into", "may", "more", "not",
    "one", "only", "still", "than", "that", "the", "their", "this", "through", "when",
    "where", "which", "who", "will", "with", "would", "your",
}


def _terms(*values: Any, limit: int = 24) -> list[str]:
    terms = {
        token.casefold()
        for value in values
        if isinstance(value, str)
        for token in TERM_PATTERN.findall(value)
        if token.casefold() not in STOPWORDS
    }
    return sorted(terms)[:limit]


def _short_text(value: Any, limit: int = 240) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return " ".join(value.split())[:limit]


def build_verdict_grounding_packet(verdict: dict[str, Any]) -> dict[str, Any]:
    source = verdict if isinstance(verdict, dict) else {}
    buyer_values = (
        source.get("buyer_pain_clarity"), source.get("willingness_to_pay_signal"),
        source.get("killer_question"), source.get("next_step"),
    )
    problem_values = (
        source.get("top_reason"), source.get("ghost_town_risk"),
        source.get("why_it_might_fail"), source.get("business_model_weakness"),
    )
    action_values = (
        source.get("next_step"), source.get("mvp_test"),
        source.get("killer_question"), source.get("willingness_to_pay_signal"),
    )
    opportunity_values = (
        source.get("why_it_might_work"), source.get("unfair_advantage_check"),
        source.get("distribution_difficulty"),
    )
    all_text = [value for value in source.values() if isinstance(value, str)]
    return {
        "idea_label": _short_text(source.get("idea_label") or source.get("idea_name"), 100),
        "idea_summary": _short_text(source.get("idea_summary"), 240),
        "verdict_label": _short_text(source.get("verdict_headline"), 120),
        "verdict_summary": _short_text(source.get("top_reason"), 240),
        "target_buyer_terms": _terms(*buyer_values),
        "problem_terms": _terms(*problem_values),
        "pain_terms": _terms(*problem_values, source.get("buyer_pain_clarity")),
        "risk_terms": _terms(
            source.get("risk_level"), source.get("ghost_town_risk"),
            source.get("why_it_might_fail"), source.get("business_model_weakness"),
        ),
        "validation_action_terms": _terms(*action_values),
        "opportunity_terms": _terms(*opportunity_values),
        "verdict_signal_terms": _terms(*all_text, limit=80),
        "forbidden_external_fact_categories": list(EXTERNAL_FACT_CATEGORIES),
    }


def grounding_packet_diagnostics(packet: dict[str, Any]) -> dict[str, Any]:
    missing = [
        field
        for field in GROUNDING_PACKET_FIELDS
        if packet.get(field) is None or packet.get(field) == []
    ]
    term_fields = (
        "target_buyer_terms", "problem_terms", "pain_terms", "risk_terms",
        "validation_action_terms", "opportunity_terms", "verdict_signal_terms",
    )
    all_terms = {
        term
        for field in term_fields
        for term in packet.get(field, [])
        if isinstance(term, str)
    }
    return {
        "grounding_packet_present": bool(packet),
        "grounding_packet_field_count": len(packet),
        "grounding_packet_missing_fields": missing,
        "grounding_terms_count": len(all_terms),
        "target_buyer_terms_count": len(packet.get("target_buyer_terms", [])),
        "pain_terms_count": len(packet.get("pain_terms", [])),
        "risk_terms_count": len(packet.get("risk_terms", [])),
        "validation_action_terms_count": len(packet.get("validation_action_terms", [])),
        "verdict_signal_terms_count": len(packet.get("verdict_signal_terms", [])),
        "opportunity_terms_count": len(packet.get("opportunity_terms", [])),
    }


def allowed_grounding_terms(packet: dict[str, Any]) -> set[str]:
    return PROJECT_TERMS | {
        term.casefold()
        for field in GROUNDING_PACKET_FIELDS
        for term in (packet.get(field) if isinstance(packet.get(field), list) else [])
        if isinstance(term, str)
    }


def classify_external_fact_signals(text: str, packet: dict[str, Any]) -> list[str]:
    value = text if isinstance(text, str) else ""
    folded = value.casefold()
    allowed = allowed_grounding_terms(packet)
    categories: set[str] = set()

    if re.search(r"(?i)\b(?:market size|tam|sam|som|billion[- ]dollar|million[- ]dollar|huge market|growing market|industry average)\b", value):
        categories.add("unsupported_market_claim")
    buyer_entities = re.findall(
        r"(?i)\b(?:fortune 500|enterprise teams?|gen z|millennials?|doctors?|lawyers?|restaurants?|retailers?)\b",
        value,
    )
    if any(not set(_terms(entity)).issubset(allowed) for entity in buyer_entities):
        categories.add("unsupported_buyer_claim")
    if re.search(r"(?i)\b\d+(?:\.\d+)?%|\b(?:conversion rate|retention rate|churn rate|daily active users?|monthly active users?)\b", value):
        categories.add("unsupported_metric_claim")
    if re.search(r"(?i)(?:\$\s*\d|\b\d+(?:\.\d+)?\s*(?:dollars?|usd|revenue|arr|mrr)\b|\b(?:revenue|arr|mrr|profit margin)\b)", value):
        categories.add("unsupported_revenue_claim")
    platforms = re.findall(
        r"(?i)\b(?:tiktok|instagram|linkedin|facebook|shopify|amazon|slack|salesforce|youtube|ios|android)\b",
        value,
    )
    if any(platform.casefold() not in allowed for platform in platforms):
        categories.add("unsupported_platform_claim")
    if re.search(r"(?i)\b(?:within|in)\s+\d+\s+(?:hours?|days?|weeks?|months?)\b|\b(?:overnight|next quarter|this year|by 20\d{2})\b", value):
        categories.add("unsupported_timing_claim")
    if re.search(r"(?i)\b(?:compete|competes|competing)\s+with\s+[A-Za-z]|\bunlike\s+[A-Z][A-Za-z0-9&.-]+", value):
        categories.add("unsupported_competitor_claim")
    if re.search(r"(?i)\b(?:guaranteed|guarantees|risk[- ]free|definitely works?|cannot fail)\b", value):
        categories.add("unsupported_guarantee_claim")
    if re.search(r"(?i)\b(?:proven demand|proven revenue|will succeed|will make money|everyone needs|guaranteed results?)\b", value):
        categories.add("unsupported_outcome_claim")
    entities = re.findall(r"\b[A-Z][A-Za-z0-9&.-]+\s+(?:Inc|Corp|LLC|Ltd)\b", value)
    if any(not set(_terms(entity)).issubset(allowed) for entity in entities):
        categories.add("unknown_entity_signal")
    return sorted(categories)


def external_fact_category_counts(categories_by_angle: list[list[str]]) -> dict[str, int]:
    counts = Counter(category for categories in categories_by_angle for category in categories)
    return {category: counts.get(category, 0) for category in EXTERNAL_FACT_CATEGORIES if counts.get(category, 0)}
