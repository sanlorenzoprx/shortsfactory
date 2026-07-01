from __future__ import annotations

from typing import Any

from .llm_bundle_schema import LLMCreativeBundleV1, REQUIRED_ANGLE_IDS


TIMESTAMPS = ("00:00", "00:30", "01:00", "01:30", "02:00", "02:30")


def normalize_llm_creative_bundle(
    bundle: LLMCreativeBundleV1,
    *,
    angle_rubric: tuple[dict[str, str], ...],
    canonical_cta: str,
) -> dict[str, Any]:
    value = bundle.to_dict()
    angles_by_id = {row["angle_id"]: row for row in value["angles"]}
    chapters_by_id = {row["angle_id"]: row for row in value["longform"]["chapters"]}
    rubric_by_id = {row["angle_id"]: dict(row) for row in angle_rubric}
    cta = canonical_cta
    transitions = list(value["longform"]["transitions"][:4])
    while len(transitions) < 4:
        transitions.append("Next, compare this angle with the same buyer evidence.")

    shorts: dict[str, dict[str, Any]] = {}
    ordered_chapters: list[dict[str, Any]] = []
    for angle_id in REQUIRED_ANGLE_IDS:
        angle = angles_by_id[angle_id]
        chapter = chapters_by_id[angle_id]
        shorts[angle_id] = {
            "title_variants": [angle["title"]],
            "hook": angle["hook"],
            "script": angle["script"],
            "caption": angle["caption"],
            "thumbnail_text": angle["thumbnail_text"],
            "cta": cta,
            "youtube_metadata_draft": {
                "angle_id": angle_id,
                "cta": cta,
                "tags": list(angle["tags"]),
                "hashtags": list(angle["hashtags"]),
                "status": "draft_not_upload_ready",
                "live_publish_enabled": False,
            },
        }
        ordered_chapters.append({
            "angle_id": angle_id,
            "chapter_title": chapter["title"],
            "chapter_script": chapter["summary"],
        })

    timestamp_labels = ["Introduction"] + [rubric_by_id[angle_id]["angle_name"] for angle_id in REQUIRED_ANGLE_IDS]
    return {
        "angles": [rubric_by_id[angle_id] for angle_id in REQUIRED_ANGLE_IDS],
        "shorts": shorts,
        "longform": {
            "longform_title": value["longform"]["title"],
            "intro_script": value["longform"]["intro"],
            "ordered_chapters": ordered_chapters,
            "transition_lines": transitions,
            "conclusion": value["longform"]["conclusion"],
            "cta_to_ghosttowntest_com": cta,
            "suggested_description": value["longform"]["description"],
            "suggested_chapters_timestamps": [
                {"timestamp": timestamp, "label": label}
                for timestamp, label in zip(TIMESTAMPS, timestamp_labels)
            ],
        },
    }
