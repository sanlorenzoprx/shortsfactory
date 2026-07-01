from __future__ import annotations

import json
import re
from typing import Any

from .creative_angle_models import AngleShortJob, CreativeAnglePack, LongFormAssemblyPlan
from .creative_providers import ANGLE_RUBRIC
from .verdict_grounding import build_verdict_grounding_packet, classify_external_fact_signals


SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]{8,}|(?:access|refresh)[_-]?token\s*[:=]\s*\S+|"
    r"client[_-]?secret\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+)"
)
AUTH_URL_PATTERN = re.compile(r"(?i)https?://[^\s\"<>]*(?:oauth|authorize|token_uri)[^\s\"<>]*")
GENERIC_CLAIM_SIGNAL = re.compile(
    r"(?i)\b(guaranteed|definitely works?|risk[- ]free|everyone needs|will make money|proven revenue)\b"
)
FORBIDDEN_PLATFORM_ACTION = re.compile(
    r"(?i)(youtube\.googleapis\.com|videos\.insert|call\s+the\s+youtube\s+api|"
    r"upload\s+(?:this|the)\s+video|publish\s+(?:this|the|now))"
)
EXPECTED_ANGLES = {row["angle_id"] for row in ANGLE_RUBRIC}
WORD_PATTERN = re.compile(r"[a-z0-9]{4,}", re.I)
GROUNDING_STOPWORDS = {
    "this", "that", "with", "from", "your", "before", "after", "could",
    "would", "should", "about", "their", "there", "business", "ghosttowntest",
}
HOOK_SIGNALS = {
    "ghost_town_risk": ("risk", "fail", "truth", "ghost town"),
    "buyer_reality": ("buyer", "pay", "customer", "market"),
    "fast_validation_test": ("test", "before", "prove", "experiment"),
    "contrarian_opportunity": ("wrong", "wedge", "opportunity", "broad"),
    "builder_action_plan": ("build", "first", "mvp", "start"),
}
BUYER_SIGNALS = ("buyer", "customer", "pay", "budget", "target")
PAIN_SIGNALS = ("pain", "risk", "fail", "problem", "urgent", "outcome")
ACTION_SIGNALS = ("test", "ask", "prove", "sell", "build", "identify", "run", "validate", "cut", "decide")
GENERIC_GROUNDING_TOKENS = GROUNDING_STOPWORDS | {
    "idea", "startup", "builder", "build", "building", "buyer", "buyers", "customer", "customers",
    "market", "pain", "risk", "problem", "urgent", "outcome", "test", "validate", "validation",
    "action", "target", "before", "after", "first", "next", "pay", "pays", "paid",
}


class CreativeGateError(ValueError):
    pass


def contains_sensitive_content(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False)
    return bool(SECRET_PATTERN.search(encoded) or AUTH_URL_PATTERN.search(encoded))


def assert_safe_provider_input(value: Any) -> None:
    if contains_sensitive_content(value):
        raise CreativeGateError("provider input contains a secret or authentication URL")


def buyer_pain_action_signals(job: AngleShortJob) -> dict[str, bool]:
    combined = f"{job.hook} {job.script}".casefold()
    canonical_cta = job.cta.strip().casefold()
    if canonical_cta:
        combined = combined.replace(canonical_cta, " ")
    return {
        "buyer_signal_present": any(signal in combined for signal in BUYER_SIGNALS),
        "pain_signal_present": any(signal in combined for signal in PAIN_SIGNALS),
        "action_signal_present": any(signal in combined for signal in ACTION_SIGNALS),
    }


def _verdict_specific_tokens(source_verdict: dict[str, Any]) -> set[str]:
    return {
        token.casefold()
        for token in WORD_PATTERN.findall(json.dumps(source_verdict, ensure_ascii=False))
        if token.casefold() not in GENERIC_GROUNDING_TOKENS
    }


def _job_grounding_text(job: AngleShortJob) -> str:
    combined = f"{job.hook} {job.script} {job.caption} {job.thumbnail_text}"
    canonical_cta = job.cta.strip()
    return re.sub(re.escape(canonical_cta), " ", combined, flags=re.IGNORECASE) if canonical_cta else combined


def _angle_intent_present(job: AngleShortJob, text: str) -> bool:
    text = text.casefold()
    buyer_present = any(signal in text for signal in BUYER_SIGNALS)
    pain_present = any(signal in text for signal in PAIN_SIGNALS)
    action_present = any(signal in text for signal in ACTION_SIGNALS)
    if job.angle_id == "ghost_town_risk":
        return pain_present and any(signal in text for signal in ("market", "buyer", "people", "care", "demand"))
    if job.angle_id == "buyer_reality":
        return buyer_present and any(signal in text for signal in ("pay", "reply", "book", "switch", "decide", "decision", "act"))
    if job.angle_id == "fast_validation_test":
        return action_present and any(signal in text for signal in (
            "result", "prove", "interest", "signal", "reply", "pay", "paid", "evidence",
        ))
    if job.angle_id == "contrarian_opportunity":
        narrow = any(signal in text for signal in ("narrow", "specific", "wedge", "use case", "workflow"))
        return narrow and buyer_present and pain_present
    if job.angle_id == "builder_action_plan":
        market_signal = buyer_present or "market" in text or "demand" in text
        return action_present and market_signal
    return False


def verdict_grounding_signals(
    job: AngleShortJob, source_verdict: dict[str, Any], grounding_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = _job_grounding_text(job)
    folded = text.casefold()
    generated_tokens = set(WORD_PATTERN.findall(folded)) - GENERIC_GROUNDING_TOKENS
    overlap = generated_tokens & _verdict_specific_tokens(source_verdict)
    packet = grounding_packet or build_verdict_grounding_packet(source_verdict)
    external_categories = classify_external_fact_signals(text, packet)
    return {
        "verdict_signal_present": len(overlap) >= 2,
        "generic_claim_signal_present": bool(GENERIC_CLAIM_SIGNAL.search(folded)),
        "external_fact_signal_present": bool(external_categories),
        "external_fact_signal_categories": external_categories,
        "idea_specificity_present": bool(overlap),
        "angle_specificity_present": _angle_intent_present(job, folded),
    }


def hook_specificity_signals(job: AngleShortJob, source_verdict: dict[str, Any]) -> dict[str, bool]:
    hook = job.hook.casefold()
    hook_tokens = set(WORD_PATTERN.findall(hook)) - GENERIC_GROUNDING_TOKENS
    return {
        "hook_generic": len(job.hook.split()) < 7,
        "hook_angle_match": any(signal in hook for signal in HOOK_SIGNALS.get(job.angle_id, ())),
        "hook_verdict_signal_present": bool(hook_tokens & _verdict_specific_tokens(source_verdict)),
    }


def _gate(name: str, passed: bool, success: str, failure: str, *, review: bool = False) -> dict[str, Any]:
    return {
        "gate_name": name,
        "status": "pass" if passed else ("needs_review" if review else "fail"),
        "blocking": not passed and not review,
        "reason": success if passed else failure,
    }


def evaluate_creative_pack(
    *,
    pack: CreativeAnglePack,
    short_jobs: tuple[AngleShortJob, ...],
    longform: LongFormAssemblyPlan,
    source_verdict: dict[str, Any],
    online_provider_explicit: bool,
) -> tuple[dict[str, Any], ...]:
    angle_ids = [angle.angle_id for angle in pack.angles]
    jobs_by_angle = {job.angle_id: job for job in short_jobs}
    grounding_packet = build_verdict_grounding_packet(source_verdict)
    gates = [
        _gate(
            "exact_five_unique_angles",
            len(angle_ids) == 5 and len(set(angle_ids)) == 5 and set(angle_ids) == EXPECTED_ANGLES,
            "all five required creative angles are present and unique",
            "creative pack must contain exactly the five required unique angle IDs",
        ),
        _gate(
            "lit_verdict_traceability",
            bool(pack.lit_verdict_id) and all(job.lit_verdict_id == pack.lit_verdict_id for job in short_jobs),
            "every short references the same stored LIT verdict",
            "one or more shorts are missing the pack LIT verdict reference",
        ),
        _gate(
            "five_complete_short_jobs",
            len(short_jobs) == 5
            and set(jobs_by_angle) == EXPECTED_ANGLES
            and all(
                all(str(value).strip() for value in (job.title, job.hook, job.script, job.caption, job.thumbnail_text, job.cta))
                for job in short_jobs
            ),
            "five complete short jobs were generated",
            "each angle requires a complete title, hook, script, caption, thumbnail text, and CTA",
        ),
    ]
    hook_analyses = {job.angle_id: hook_specificity_signals(job, source_verdict) for job in short_jobs}
    hook_failures = [
        job.angle_id for job in short_jobs
        if hook_analyses[job.angle_id]["hook_generic"]
        or not hook_analyses[job.angle_id]["hook_angle_match"]
        or not hook_analyses[job.angle_id]["hook_verdict_signal_present"]
    ]
    gates.append(_gate(
        "specific_hooks",
        not hook_failures,
        "every hook is specific to its angle",
        "generic or mismatched hooks: " + ", ".join(hook_failures),
    ))
    content_failures = [
        job.angle_id
        for job in short_jobs
        if not all(buyer_pain_action_signals(job).values())
    ]
    gates.append(_gate(
        "buyer_pain_action_specificity",
        not content_failures,
        "every short names buyer reality, pain/risk, and a concrete action",
        "missing buyer, pain, or action specificity: " + ", ".join(content_failures),
    ))
    verdict_analyses = {
        job.angle_id: verdict_grounding_signals(job, source_verdict, grounding_packet)
        for job in short_jobs
    }
    claim_failures = [
        job.angle_id for job in short_jobs
        if not verdict_analyses[job.angle_id]["verdict_signal_present"]
        or verdict_analyses[job.angle_id]["generic_claim_signal_present"]
        or verdict_analyses[job.angle_id]["external_fact_signal_present"]
        or not verdict_analyses[job.angle_id]["idea_specificity_present"]
        or not verdict_analyses[job.angle_id]["angle_specificity_present"]
    ]
    gates.append(_gate(
        "verdict_grounded_claims",
        not claim_failures,
        "every angle is specific to the stored verdict and avoids unsupported claims",
        "angles lack verdict grounding or contain unsupported claims: " + ", ".join(claim_failures),
    ))
    source_tokens = {
        token.casefold() for token in WORD_PATTERN.findall(json.dumps(source_verdict, ensure_ascii=False))
        if token.casefold() not in GROUNDING_STOPWORDS
    }
    low_overlap = []
    for job in short_jobs:
        generated_tokens = {
            token.casefold() for token in WORD_PATTERN.findall(f"{job.hook} {job.script}")
            if token.casefold() not in GROUNDING_STOPWORDS
        }
        if len(source_tokens & generated_tokens) < 2:
            low_overlap.append(job.angle_id)
    gates.append(_gate(
        "source_grounding_overlap",
        not low_overlap,
        "every script retains concrete overlap with the stored LIT verdict",
        "scripts require human grounding review: " + ", ".join(low_overlap),
        review=True,
    ))
    canonical_cta = longform.cta_to_ghosttowntest_com
    cta_failures = [
        job.angle_id for job in short_jobs
        if job.cta != canonical_cta
        or canonical_cta not in job.script
        or canonical_cta not in job.caption
        or job.youtube_metadata_draft.get("cta") != canonical_cta
        or "GhostTownTest.com" not in job.cta
    ]
    gates.append(_gate(
        "ghost_town_cta",
        not cta_failures and "GhostTownTest.com" in canonical_cta,
        "all short and long-form content uses the canonical GhostTownTest.com CTA",
        "CTA is missing or malformed in: " + ", ".join(cta_failures or ["long_form"]),
    ))
    title_failures = [job.angle_id for job in short_jobs if not job.title or len(job.title) > 100]
    gates.append(_gate(
        "youtube_titles",
        not title_failures and 0 < len(longform.longform_title) <= 100,
        "all titles are present and within YouTube limits",
        "missing or overlong titles: " + ", ".join(title_failures or ["long_form"]),
    ))
    thumbnail_failures = [
        job.angle_id for job in short_jobs
        if len(job.thumbnail_text.split()) < 3 or len(job.thumbnail_text) > 60
    ]
    gates.append(_gate(
        "thumbnail_specificity",
        not thumbnail_failures,
        "thumbnail text is concise and specific",
        "thumbnail text is vague or overlong: " + ", ".join(thumbnail_failures),
    ))
    metadata_failures = [
        job.angle_id for job in short_jobs
        if not job.tags
        or not job.hashtags
        or not job.youtube_metadata_draft.get("tags")
        or not job.youtube_metadata_draft.get("hashtags")
        or job.youtube_metadata_draft.get("angle_id") != job.angle_id
        or job.youtube_metadata_draft.get("source_job_id") != job.job_id
        or job.youtube_metadata_draft.get("idea_id") != job.idea_id
        or job.youtube_metadata_draft.get("lit_verdict_id") != job.lit_verdict_id
        or job.youtube_metadata_draft.get("platform") != "youtube_shorts"
        or job.youtube_metadata_draft.get("live_publish_enabled") is not False
    ]
    gates.append(_gate(
        "youtube_metadata_drafts",
        not metadata_failures,
        "every YouTube draft includes angle identity, tags, hashtags, and live publishing disabled",
        "invalid YouTube metadata drafts: " + ", ".join(metadata_failures),
    ))
    gates.append(_gate(
        "longform_assembly",
        len(longform.source_short_job_ids) == 5
        and tuple(job.job_id for job in short_jobs) == longform.source_short_job_ids
        and {chapter.get("angle_id") for chapter in longform.ordered_chapters} == EXPECTED_ANGLES,
        "long-form plan includes all five source shorts in order",
        "long-form plan does not include all five angles and source short IDs",
    ))
    output_value = {
        "pack": pack.to_dict(),
        "short_jobs": [job.to_dict() for job in short_jobs],
        "longform": longform.to_dict(),
    }
    gates.append(_gate(
        "secret_redaction",
        not contains_sensitive_content(output_value),
        "validated artifacts contain no secrets or authentication URLs",
        "a secret or authentication URL appears in generated content",
    ))
    gates.append(_gate(
        "no_platform_actions",
        not FORBIDDEN_PLATFORM_ACTION.search(json.dumps(output_value, ensure_ascii=False)),
        "LLM output contains no publishing or YouTube API action",
        "LLM output attempted to request publishing or a YouTube API call",
    ))
    gates.append(_gate(
        "online_provider_explicit",
        pack.provider_type != "online_llm" or online_provider_explicit,
        "online provider was not used or was selected explicitly",
        "online provider use requires an explicit provider flag",
    ))
    gates.append(_gate(
        "publishing_closed",
        all(job.live_publish_enabled is False for job in short_jobs)
        and longform.live_publish_enabled is False
        and all(job.youtube_metadata_draft.get("status") == "draft_not_upload_ready" for job in short_jobs),
        "all creative artifacts remain non-publishing drafts",
        "creative generation attempted to create upload-ready or live artifacts",
    ))
    return tuple(gates)
