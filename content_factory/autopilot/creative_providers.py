from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .creative_generation_provider import CreativeGenerationContext, CreativeGenerationProvider, JsonDict
from .llm_model_registry import LLMModelProfile
from .llm_provider_adapters import LLMAdapterError, LLMProviderAdapter


CTA = "Test your business idea at GhostTownTest.com."
RUBRIC_VERSION = "creative-angle-rubric.v1"
PROMPT_PREFIX = (
    "You create evidence-grounded business validation content. Return only the requested JSON. "
    "Use the supplied LIT verdict as the factual boundary. Do not invent numbers, customers, revenue, "
    "market size, or certainty. Every output must remain a draft and must never request publishing."
)

ANGLE_RUBRIC = (
    {
        "angle_id": "ghost_town_risk",
        "angle_name": "Ghost Town Risk",
        "purpose": "explain why the idea may fail",
        "hook_style": "warning / risk / painful truth",
        "target_emotion": "caution",
        "viewer_question": "What could make this idea fail even if it sounds useful?",
        "expected_behavior_signal": "viewer compares the risk with a real buying decision",
    },
    {
        "angle_id": "buyer_reality",
        "angle_name": "Buyer Reality",
        "purpose": "identify who actually pays and why",
        "hook_style": "buyer truth / market reality",
        "target_emotion": "recognition",
        "viewer_question": "Who owns this pain strongly enough to pay?",
        "expected_behavior_signal": "viewer names the buyer, budget owner, and urgent pain",
    },
    {
        "angle_id": "fast_validation_test",
        "angle_name": "Fast Validation Test",
        "purpose": "give the smallest test before building",
        "hook_style": "action / experiment / proof",
        "target_emotion": "agency",
        "viewer_question": "What is the smallest paid test I can run now?",
        "expected_behavior_signal": "viewer runs or saves the proposed validation experiment",
    },
    {
        "angle_id": "contrarian_opportunity",
        "angle_name": "Contrarian Opportunity",
        "purpose": "show the better wedge or hidden opportunity",
        "hook_style": "contrarian / reframing",
        "target_emotion": "curiosity",
        "viewer_question": "Is the narrow wedge more valuable than the broad idea?",
        "expected_behavior_signal": "viewer reframes the offer around one painful outcome",
    },
    {
        "angle_id": "builder_action_plan",
        "angle_name": "Builder Action Plan",
        "purpose": "explain what to build first if the idea is still worth testing",
        "hook_style": "practical / next step / MVP",
        "target_emotion": "clarity",
        "viewer_question": "What should I build first without overbuilding?",
        "expected_behavior_signal": "viewer scopes an MVP to one buyer and measurable result",
    },
)


class CreativeProviderError(RuntimeError):
    pass


def _clean(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text or fallback


def _sentence(value: Any, fallback: str) -> str:
    return _clean(value, fallback).rstrip(".?!") + "."


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip(" ,:;-") + "…"


class DeterministicCreativeGenerationProvider(CreativeGenerationProvider):
    provider_type = "deterministic"
    model_id = None
    prompt_prefix = PROMPT_PREFIX + " Deterministic local templates only."
    network_called = False

    def generate_angle_pack(self, context: CreativeGenerationContext) -> list[JsonDict]:
        return deepcopy(list(ANGLE_RUBRIC))

    def _content(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        idea = context.idea
        verdict = context.verdict_record.verdict
        name = _clean(idea.name, "This business idea")
        target = _clean(idea.target_user, "the intended buyer")
        risk = _sentence(
            verdict.get("why_it_might_fail") or verdict.get("ghost_town_risk") or verdict.get("top_reason"),
            "Demand may disappear when the offer reaches a real buying decision",
        )
        buyer = _sentence(
            verdict.get("buyer_pain_clarity") or verdict.get("willingness_to_pay_signal"),
            f"The likely buyer is {target}, but urgency and budget still need direct proof",
        )
        test = _sentence(
            verdict.get("mvp_test") or verdict.get("next_step"),
            "Ask five target buyers for a paid pilot before building software",
        )
        opportunity = _sentence(
            verdict.get("why_it_might_work") or verdict.get("unfair_advantage_check"),
            f"The stronger wedge may be one painful workflow for {target}, not a broad platform",
        )
        build = _sentence(
            verdict.get("next_step") or verdict.get("business_model_weakness"),
            "Build only the smallest deliverable needed to complete one paid customer outcome",
        )
        return {
            "ghost_town_risk": {
                "hook": f"Painful truth: {name} could become a ghost town before the first customer pays.",
                "title": f"Why {name} Could Fail",
                "body": [risk, "A good-sounding problem is not the same as a budgeted problem.", "Prove urgency with a payment decision, not compliments."],
                "thumbnail": "WHY THIS IDEA MAY FAIL",
            },
            "buyer_reality": {
                "hook": f"The user is not always the buyer—and that can kill {name}.",
                "title": f"Who Actually Pays for {name}?",
                "body": [buyer, f"Start with {target} and identify who owns the pain, budget, and approval.", "If those are different people, the sales motion is part of the product risk."],
                "thumbnail": "WHO ACTUALLY PAYS?",
            },
            "fast_validation_test": {
                "hook": f"Before you build {name}, run this tiny paid test.",
                "title": f"Test {name} Before Building",
                "body": [test, f"Ask target buyers—{target}—about one painful outcome and a price for delivering it manually.", "A paid yes is evidence; a polite maybe is not."],
                "thumbnail": "RUN THIS TEST FIRST",
            },
            "contrarian_opportunity": {
                "hook": f"The broad version of {name} may be wrong—but the narrow wedge could be valuable.",
                "title": f"The Hidden Opportunity in {name}",
                "body": [opportunity, f"Sell one painful outcome to a buyer in {target}, then learn which repeated step deserves automation.", "The opportunity is specificity, not more features."],
                "thumbnail": "THE BETTER WEDGE",
            },
            "builder_action_plan": {
                "hook": f"If {name} is still worth testing, build this first—not the full product.",
                "title": f"The First MVP for {name}",
                "body": [build, f"Keep the MVP tied to one buyer in {target}, one painful moment, and one measurable result.", "Do the workflow manually until repeat demand tells you what to automate."],
                "thumbnail": "BUILD THIS FIRST",
            },
        }[angle["angle_id"]]

    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        content = self._content(context, angle)
        hook = _clip(content["hook"], 220)
        return {"hook": hook, "script": "\n\n".join([hook, *content["body"], CTA]), "cta": CTA}

    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        primary = _clip(self._content(context, angle)["title"], 100)
        return [primary, _clip(f"Ghost Town Test: {angle['angle_name']} for {context.idea.name}", 100)]

    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        return self._content(context, angle)["thumbnail"]

    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        content = self._content(context, angle)
        return _clip(f"{content['hook']} {content['body'][0]} {CTA}", 500)

    def generate_youtube_metadata_draft(
        self, context: CreativeGenerationContext, angle: JsonDict, short_content: JsonDict,
    ) -> JsonDict:
        return {
            "schema_version": "youtube_metadata_draft.v1",
            "platform": "youtube_shorts",
            "idea_id": context.idea.idea_id,
            "lit_verdict_id": context.lit_verdict_id,
            "angle_id": angle["angle_id"],
            "title": short_content["title"],
            "description": f"{short_content['caption']}\n\n{short_content['cta']}",
            "caption": short_content["caption"],
            "thumbnail_text": short_content["thumbnail_text"],
            "cta": short_content["cta"],
            "cta_text": short_content["cta"],
            "tags": list(short_content["tags"]),
            "hashtags": list(short_content["hashtags"]),
            "category_id": "22",
            "privacy_status": "private",
            "made_for_kids": False,
            "status": "draft_not_upload_ready",
            "live_publish_enabled": False,
        }

    def generate_longform_assembly_plan(
        self, context: CreativeGenerationContext, short_jobs: list[JsonDict],
    ) -> JsonDict:
        headline = _clean(context.verdict_record.verdict.get("verdict_headline"), "The idea needs a real market test")
        timestamps = ("00:30", "01:45", "03:00", "04:15", "05:30")
        return {
            "longform_title": _clip(
                f"{context.idea.name}: Risk, Buyer, Validation, Opportunity, and MVP", 100,
            ),
            "intro_script": (
                f"Is {context.idea.name} worth building, or is it another future ghost town? "
                f"The LIT verdict is: {headline}. We’ll examine the risk, buyer, fastest test, hidden wedge, and first MVP."
            ),
            "ordered_chapters": [
                {
                    "order": index,
                    "angle_id": job["angle_id"],
                    "job_id": job["job_id"],
                    "chapter_title": job["title"],
                    "chapter_script": job["script"],
                }
                for index, job in enumerate(short_jobs, 1)
            ],
            "transition_lines": [
                "That is the failure risk. Now let’s identify the person who would actually pay.",
                "Buyer reality gives us a hypothesis; the next chapter turns it into a fast test.",
                "The test tells us what not to build—and reveals the narrower opportunity.",
                "With the wedge clear, we can define the smallest useful first build.",
            ],
            "conclusion": (
                "Do not confuse a complete build with a validated business. Run the smallest paid test that can "
                "disprove the riskiest assumption, and build further only when buyer behavior earns it."
            ),
            "cta_to_ghosttowntest_com": CTA,
            "suggested_description": (
                f"A five-angle Ghost Town Test breakdown of {context.idea.name}: failure risk, buyer reality, "
                f"fast validation, the better wedge, and a practical MVP plan.\n\n{CTA}"
            ),
            "suggested_chapters_timestamps": [
                {"timestamp": "00:00", "label": "The Ghost Town Test verdict"},
                *[
                    {"timestamp": timestamp, "label": job["title"], "job_id": job["job_id"]}
                    for timestamp, job in zip(timestamps, short_jobs)
                ],
            ],
        }


class FixtureCreativeGenerationProvider(CreativeGenerationProvider):
    provider_type = "fixture"
    model_id = None
    prompt_prefix = PROMPT_PREFIX + " Checked-in fixture outputs only."
    network_called = False

    def __init__(self, creative_output: JsonDict):
        if not isinstance(creative_output, dict):
            raise CreativeProviderError("fixture provider requires creative_output fixture data")
        self.output = deepcopy(creative_output)

    def _short(self, angle: JsonDict) -> JsonDict:
        value = self.output.get("shorts", {}).get(angle["angle_id"])
        if not isinstance(value, dict):
            raise CreativeProviderError(f"fixture short is missing for {angle['angle_id']}")
        return deepcopy(value)

    def generate_angle_pack(self, context: CreativeGenerationContext) -> list[JsonDict]:
        angles = self.output.get("angles")
        if not isinstance(angles, list):
            raise CreativeProviderError("fixture angles are missing")
        return deepcopy(angles)

    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        short = self._short(angle)
        return {key: short.get(key) for key in ("hook", "script", "cta")}

    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        value = self._short(angle).get("title_variants")
        return deepcopy(value) if isinstance(value, list) else []

    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        return str(self._short(angle).get("thumbnail_text", ""))

    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        return str(self._short(angle).get("caption", ""))

    def generate_youtube_metadata_draft(
        self, context: CreativeGenerationContext, angle: JsonDict, short_content: JsonDict,
    ) -> JsonDict:
        value = self._short(angle).get("youtube_metadata_draft")
        if not isinstance(value, dict):
            raise CreativeProviderError(f"fixture YouTube metadata is missing for {angle['angle_id']}")
        return deepcopy(value)

    def generate_longform_assembly_plan(
        self, context: CreativeGenerationContext, short_jobs: list[JsonDict],
    ) -> JsonDict:
        value = self.output.get("longform")
        if not isinstance(value, dict):
            raise CreativeProviderError("fixture long-form plan is missing")
        plan = deepcopy(value)
        for index, chapter in enumerate(plan.get("ordered_chapters", [])):
            if index < len(short_jobs):
                chapter["job_id"] = short_jobs[index]["job_id"]
        return plan


class OnlineLLMCreativeGenerationProvider(CreativeGenerationProvider):
    provider_type = "online_llm"
    prompt_prefix = PROMPT_PREFIX

    def __init__(
        self,
        profile: LLMModelProfile,
        adapter: LLMProviderAdapter,
    ):
        if not profile.enabled:
            raise CreativeProviderError(f"model is disabled: {profile.model_id}")
        if not profile.supports_json_schema:
            raise CreativeProviderError(f"model lacks required JSON schema capability: {profile.model_id}")
        self.profile = profile
        self.adapter = adapter
        self.model_id = profile.model_id
        self.model_provider = profile.provider
        self.model_profile_hash = profile.profile_hash
        self.adapter_type = adapter.adapter_type

    @property
    def network_called(self) -> bool:
        return self.adapter.network_called

    @property
    def tokens_used(self) -> int:
        return self.adapter.estimated_input_tokens + self.adapter.estimated_output_tokens

    @property
    def cost_estimate(self) -> float:
        return self.adapter.estimated_cost

    @property
    def estimated_input_tokens(self) -> int:
        return self.adapter.estimated_input_tokens

    @property
    def estimated_output_tokens(self) -> int:
        return self.adapter.estimated_output_tokens

    @property
    def estimated_cost(self) -> float:
        return self.adapter.estimated_cost

    @property
    def raw_response_stored(self) -> bool:
        return self.adapter.raw_response_stored

    def _call(self, task: str, payload: JsonDict, schema: JsonDict) -> Any:
        prompt = json.dumps(
            {"system_prefix": self.prompt_prefix, "task": task, "input": payload},
            ensure_ascii=False,
        )
        try:
            return self.adapter.generate_json(prompt, schema, self.profile)
        except LLMAdapterError as exc:
            raise CreativeProviderError(f"LLM adapter rejected {task}: {exc}") from exc

    def generate_angle_pack(self, context: CreativeGenerationContext) -> list[JsonDict]:
        angle_properties = {
            "angle_id": {"type": "string"},
            "angle_name": {"type": "string"},
            "purpose": {"type": "string"},
            "hook_style": {"type": "string"},
            "target_emotion": {"type": "string"},
            "viewer_question": {"type": "string"},
            "expected_behavior_signal": {"type": "string"},
        }
        value = self._call(
            "generate_angle_pack",
            {**context.provider_input(), "required_angles": list(ANGLE_RUBRIC)},
            {
                "type": "object",
                "properties": {
                    "angles": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": angle_properties,
                            "required": list(angle_properties),
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["angles"],
                "additionalProperties": False,
            },
        )
        angles = value.get("angles") if isinstance(value, dict) else value
        if not isinstance(angles, list):
            raise CreativeProviderError("online angle pack is invalid")
        return angles

    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        value = self._call(
            "generate_short_script",
            {**context.provider_input(), "angle": angle, "required_cta": CTA},
            {
                "type": "object",
                "properties": {key: {"type": "string"} for key in ("hook", "script", "cta")},
                "required": ["hook", "script", "cta"],
                "additionalProperties": False,
            },
        )
        if not isinstance(value, dict):
            raise CreativeProviderError("online short script is invalid")
        return value

    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        value = self._call(
            "generate_title_variants",
            {**context.provider_input(), "angle": angle, "max_length": 100},
            {
                "type": "object",
                "properties": {"title_variants": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                "required": ["title_variants"],
                "additionalProperties": False,
            },
        )
        variants = value.get("title_variants") if isinstance(value, dict) else value
        if not isinstance(variants, list):
            raise CreativeProviderError("online title variants are invalid")
        return variants

    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        value = self._call(
            "generate_thumbnail_text",
            {**context.provider_input(), "angle": angle},
            {
                "type": "object",
                "properties": {"thumbnail_text": {"type": "string"}},
                "required": ["thumbnail_text"],
                "additionalProperties": False,
            },
        )
        return str(value.get("thumbnail_text", "")) if isinstance(value, dict) else str(value)

    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        value = self._call(
            "generate_caption",
            {**context.provider_input(), "angle": angle, "required_cta": CTA},
            {
                "type": "object",
                "properties": {"caption": {"type": "string"}},
                "required": ["caption"],
                "additionalProperties": False,
            },
        )
        return str(value.get("caption", "")) if isinstance(value, dict) else str(value)

    def generate_youtube_metadata_draft(
        self, context: CreativeGenerationContext, angle: JsonDict, short_content: JsonDict,
    ) -> JsonDict:
        value = self._call(
            "generate_youtube_metadata_draft",
            {**context.provider_input(), "angle": angle, "short": short_content, "status": "draft_not_upload_ready"},
            {
                "type": "object",
                "properties": {
                    "angle_id": {"type": "string"},
                    "cta": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "status": {"type": "string"},
                    "live_publish_enabled": {"type": "boolean"},
                },
                "required": ["angle_id", "cta", "tags", "hashtags", "status", "live_publish_enabled"],
                "additionalProperties": False,
            },
        )
        if not isinstance(value, dict):
            raise CreativeProviderError("online YouTube metadata draft is invalid")
        return value

    def generate_longform_assembly_plan(
        self, context: CreativeGenerationContext, short_jobs: list[JsonDict],
    ) -> JsonDict:
        value = self._call(
            "generate_longform_assembly_plan",
            {**context.provider_input(), "short_jobs": short_jobs, "required_cta": CTA},
            {
                "type": "object",
                "properties": {
                    key: {"type": "string"}
                    for key in (
                        "longform_title", "intro_script", "conclusion",
                        "cta_to_ghosttowntest_com", "suggested_description",
                    )
                } | {
                    "ordered_chapters": {
                        "type": "array", "minItems": 5, "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "order": {"type": "integer"},
                                "angle_id": {"type": "string"},
                                "job_id": {"type": "string"},
                                "chapter_title": {"type": "string"},
                                "chapter_script": {"type": "string"},
                            },
                            "required": ["order", "angle_id", "job_id", "chapter_title", "chapter_script"],
                            "additionalProperties": False,
                        },
                    },
                    "transition_lines": {
                        "type": "array", "minItems": 4, "maxItems": 4,
                        "items": {"type": "string"},
                    },
                    "suggested_chapters_timestamps": {
                        "type": "array", "minItems": 6, "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": "string"},
                                "label": {"type": "string"},
                                "job_id": {"type": ["string", "null"]},
                            },
                            "required": ["timestamp", "label"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "longform_title", "intro_script", "ordered_chapters", "transition_lines",
                    "conclusion", "cta_to_ghosttowntest_com", "suggested_description",
                    "suggested_chapters_timestamps",
                ],
                "additionalProperties": False,
            },
        )
        if not isinstance(value, dict):
            raise CreativeProviderError("online long-form plan is invalid")
        return value
