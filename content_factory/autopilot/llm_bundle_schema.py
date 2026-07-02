from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


REQUIRED_ANGLE_IDS = (
    "ghost_town_risk",
    "buyer_reality",
    "fast_validation_test",
    "contrarian_opportunity",
    "builder_action_plan",
)
TOP_LEVEL_FIELDS = ("idea_summary", "verdict_summary", "cta", "angles", "longform")
ANGLE_FIELDS = ("angle_id", "title", "hook", "script", "caption", "thumbnail_text", "tags", "hashtags")
LONGFORM_FIELDS = ("title", "intro", "chapters", "transitions", "conclusion", "description")
CHAPTER_FIELDS = ("angle_id", "title", "summary")


class LLMBundleValidationError(ValueError):
    def __init__(self, paths: list[str]):
        super().__init__("compact creative bundle is invalid")
        self.paths = paths


ANGLE_STRING_LIMITS = {
    "hook": 120,
    "script": 450,
    "caption": 180,
    "thumbnail_text": 36,
}


@dataclass(frozen=True)
class LLMCreativeAngleV1:
    value: dict[str, Any]

    @classmethod
    def validate(cls, value: Any, *, expected_angle_id: str | None = None) -> "LLMCreativeAngleV1":
        errors: list[str] = []
        if not isinstance(value, dict):
            raise LLMBundleValidationError(["$"])
        for field in ANGLE_FIELDS:
            if field not in value:
                errors.append(f"$.{field}")
        for field in sorted(set(value) - set(ANGLE_FIELDS)):
            errors.append(f"$.{field}")
        for field in ("angle_id", "title", "hook", "script", "caption", "thumbnail_text"):
            field_value = value.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                errors.append(f"$.{field}")
            elif field in ANGLE_STRING_LIMITS and len(field_value) > ANGLE_STRING_LIMITS[field]:
                errors.append(f"$.{field}")
        angle_id = value.get("angle_id")
        if angle_id not in REQUIRED_ANGLE_IDS or (
            expected_angle_id is not None and angle_id != expected_angle_id
        ):
            errors.append("$.angle_id")
        for field in ("tags", "hashtags"):
            items = value.get(field)
            if (
                not isinstance(items, list)
                or not items
                or len(items) > 4
                or any(not isinstance(item, str) or not item.strip() for item in items)
            ):
                errors.append(f"$.{field}")
        if errors:
            raise LLMBundleValidationError(sorted(set(errors)))
        return cls(deepcopy(value))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.value)


@dataclass(frozen=True)
class LLMCreativeBundleV1:
    value: dict[str, Any]

    @classmethod
    def validate(cls, value: Any) -> "LLMCreativeBundleV1":
        errors: list[str] = []
        if not isinstance(value, dict):
            raise LLMBundleValidationError(["$"])
        for field in TOP_LEVEL_FIELDS:
            if field not in value:
                errors.append(f"$.{field}")
        for field in ("idea_summary", "verdict_summary", "cta"):
            if field in value and (not isinstance(value[field], str) or not value[field].strip()):
                errors.append(f"$.{field}")
        if isinstance(value.get("cta"), str) and "ghosttowntest.com" not in value["cta"].casefold():
            errors.append("$.cta")

        angles = value.get("angles")
        angle_ids: list[str] = []
        if not isinstance(angles, list):
            errors.append("$.angles")
        else:
            if len(angles) != 5:
                errors.append("$.angles")
            for index, angle in enumerate(angles):
                path = f"$.angles[{index}]"
                if not isinstance(angle, dict):
                    errors.append(path)
                    continue
                for field in ANGLE_FIELDS:
                    if field not in angle:
                        errors.append(f"{path}.{field}")
                for field in ("angle_id", "title", "hook", "script", "caption", "thumbnail_text"):
                    if field in angle and (not isinstance(angle[field], str) or not angle[field].strip()):
                        errors.append(f"{path}.{field}")
                for field in ("tags", "hashtags"):
                    items = angle.get(field)
                    if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item.strip() for item in items):
                        errors.append(f"{path}.{field}")
                if isinstance(angle.get("angle_id"), str):
                    angle_ids.append(angle["angle_id"])
            if len(set(angle_ids)) != len(angle_ids) or set(angle_ids) != set(REQUIRED_ANGLE_IDS):
                errors.append("$.angles[].angle_id")

        longform = value.get("longform")
        if not isinstance(longform, dict):
            errors.append("$.longform")
        else:
            for field in LONGFORM_FIELDS:
                if field not in longform:
                    errors.append(f"$.longform.{field}")
            for field in ("title", "intro", "conclusion", "description"):
                if field in longform and (not isinstance(longform[field], str) or not longform[field].strip()):
                    errors.append(f"$.longform.{field}")
            transitions = longform.get("transitions")
            if not isinstance(transitions, list) or any(not isinstance(item, str) for item in transitions):
                errors.append("$.longform.transitions")
            chapters = longform.get("chapters")
            chapter_ids: list[str] = []
            if not isinstance(chapters, list) or len(chapters) != 5:
                errors.append("$.longform.chapters")
            else:
                for index, chapter in enumerate(chapters):
                    path = f"$.longform.chapters[{index}]"
                    if not isinstance(chapter, dict):
                        errors.append(path)
                        continue
                    for field in CHAPTER_FIELDS:
                        if field not in chapter:
                            errors.append(f"{path}.{field}")
                    for field in CHAPTER_FIELDS:
                        if field in chapter and (not isinstance(chapter[field], str) or not chapter[field].strip()):
                            errors.append(f"{path}.{field}")
                    if isinstance(chapter.get("angle_id"), str):
                        chapter_ids.append(chapter["angle_id"])
                if len(set(chapter_ids)) != len(chapter_ids) or set(chapter_ids) != set(REQUIRED_ANGLE_IDS):
                    errors.append("$.longform.chapters[].angle_id")
        if errors:
            raise LLMBundleValidationError(errors)
        return cls(deepcopy(value))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.value)


LLM_CREATIVE_BUNDLE_V1_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {field: {} for field in TOP_LEVEL_FIELDS},
}


LLM_CREATIVE_ANGLE_V1_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "angle_id": {"type": "string", "enum": list(REQUIRED_ANGLE_IDS)},
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "script": {"type": "string"},
        "caption": {"type": "string"},
        "thumbnail_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
        "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
    },
    "required": list(ANGLE_FIELDS),
    "additionalProperties": False,
}
