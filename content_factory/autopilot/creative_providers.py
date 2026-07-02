from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Callable

from .creative_generation_provider import CreativeGenerationContext, CreativeGenerationProvider, JsonDict
from .llm_model_registry import LLMModelProfile
from .llm_provider_adapters import (
    LLMAdapterError,
    LLMProviderAdapter,
    SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS,
)
from .llm_bundle_normalizer import normalize_llm_creative_bundle
from .llm_bundle_schema import (
    LLM_CREATIVE_BUNDLE_V1_JSON_SCHEMA,
    LLM_CREATIVE_ANGLE_V1_JSON_SCHEMA,
    LLMBundleValidationError,
    LLMCreativeAngleV1,
    LLMCreativeBundleV1,
    REQUIRED_ANGLE_IDS,
)
from .provider_diagnostics import ProviderContentDiagnostics
from .verdict_grounding import build_verdict_grounding_packet


CTA = "Run your idea through the Ghost Town Test at GhostTownTest.com"
SPLIT_GENERATION_STRATEGY = "per_angle_v1"
SPLIT_BUDGET_PROFILE = "compact_angle_v1"
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
        local_client_validation = profile.allow_localhost and profile.endpoint_type == "chat_json"
        if not profile.supports_json_schema and not local_client_validation:
            raise CreativeProviderError(f"model lacks required JSON schema capability: {profile.model_id}")
        self.profile = profile
        self.adapter = adapter
        self.model_id = profile.model_id
        self.model_provider = profile.provider
        self.model_profile_hash = profile.profile_hash
        self.adapter_type = adapter.adapter_type
        self._bundle: JsonDict | None = None
        self.idea_summary: str | None = None
        self.verdict_summary: str | None = None
        self._grounding_packet: JsonDict = {}

    @property
    def network_called(self) -> bool:
        return self.adapter.network_called

    @property
    def tokens_used(self) -> int | None:
        return self.adapter.tokens_used

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

    @property
    def provider_reported_cost(self) -> float | None:
        return self.adapter.provider_reported_cost

    @property
    def provider_diagnostics(self) -> JsonDict:
        return self.adapter.provider_diagnostics.to_dict()

    def mark_internal_schema_valid(self) -> None:
        self.adapter.provider_diagnostics.internal_schema_valid = True
        self.adapter.provider_diagnostics.parse_error_type = None
        self.adapter.provider_diagnostics.schema_error_type = None
        self.adapter.provider_diagnostics.missing_required_fields = []
        self.adapter.provider_diagnostics.schema_error_count = 0

    def mark_internal_schema_invalid(self, paths: list[str] | None = None) -> None:
        self.adapter.provider_diagnostics.internal_schema_valid = False
        self.adapter.provider_diagnostics.record_schema_failure("internal_schema_invalid", paths or ["$"])

    def mark_quality_result(
        self,
        *,
        quality_valid: bool,
        gates: tuple[JsonDict, ...],
        required_angle_ids: list[str],
        angle_ids: list[str],
        short_summaries: list[JsonDict],
        longform_present: bool,
        longform_cta_present: bool,
        longform_ghosttowntest_cta_present: bool,
    ) -> None:
        self.adapter.provider_diagnostics.record_grounding_packet(self._grounding_packet)
        self.adapter.provider_diagnostics.record_quality_result(
            quality_valid=quality_valid,
            gates=gates,
            required_angle_ids=required_angle_ids,
            angle_ids=angle_ids,
            short_summaries=short_summaries,
            longform_present=longform_present,
            longform_cta_present=longform_cta_present,
            longform_ghosttowntest_cta_present=longform_ghosttowntest_cta_present,
        )

    def mark_quality_invalid(
        self,
        *,
        gates: tuple[JsonDict, ...],
        required_angle_ids: list[str],
        angle_ids: list[str],
        short_summaries: list[JsonDict],
        longform_present: bool,
        longform_cta_present: bool,
        longform_ghosttowntest_cta_present: bool,
    ) -> None:
        self.mark_quality_result(
            quality_valid=False,
            gates=gates,
            required_angle_ids=required_angle_ids,
            angle_ids=angle_ids,
            short_summaries=short_summaries,
            longform_present=longform_present,
            longform_cta_present=longform_cta_present,
            longform_ghosttowntest_cta_present=longform_ghosttowntest_cta_present,
        )

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
        angles = self._ensure_bundle(context).get("angles")
        if not isinstance(angles, list):
            raise CreativeProviderError("online angle pack is invalid")
        return deepcopy(angles)

    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        short = self._short(context, angle)
        return {key: deepcopy(short.get(key)) for key in ("hook", "script", "cta")}

    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        variants = self._short(context, angle).get("title_variants")
        if not isinstance(variants, list):
            raise CreativeProviderError("online title variants are invalid")
        return deepcopy(variants)

    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        return str(self._short(context, angle).get("thumbnail_text", ""))

    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        return str(self._short(context, angle).get("caption", ""))

    def generate_youtube_metadata_draft(
        self, context: CreativeGenerationContext, angle: JsonDict, short_content: JsonDict,
    ) -> JsonDict:
        value = self._short(context, angle).get("youtube_metadata_draft")
        if not isinstance(value, dict):
            raise CreativeProviderError("online YouTube metadata draft is invalid")
        return deepcopy(value)

    def generate_longform_assembly_plan(
        self, context: CreativeGenerationContext, short_jobs: list[JsonDict],
    ) -> JsonDict:
        value = deepcopy(self._ensure_bundle(context).get("longform"))
        if not isinstance(value, dict):
            raise CreativeProviderError("online long-form plan is invalid")
        jobs_by_angle = {job.get("angle_id"): job for job in short_jobs}
        for index, chapter in enumerate(value.get("ordered_chapters", []), 1):
            if not isinstance(chapter, dict):
                continue
            chapter["order"] = index
            source_job = jobs_by_angle.get(chapter.get("angle_id"), {})
            chapter["job_id"] = source_job.get("job_id")
        return value

    def _ensure_bundle(self, context: CreativeGenerationContext) -> JsonDict:
        if self._bundle is None:
            payload = {
                    "lit_verdict_id": context.lit_verdict_id,
                    "lit_verdict": context.verdict_record.verdict,
                    "required_angles": list(ANGLE_RUBRIC),
                    "brand_context": {
                        "brand": "Ghost Town Test",
                        "website": "GhostTownTest.com",
                        "audience": context.idea.target_user,
                        "market": context.idea.market,
                    },
                    "requirements": {
                        "exactly_five_angles": True,
                        "one_short_per_angle": True,
                        "one_longform_assembly_plan": True,
                        "canonical_cta": CTA,
                        "youtube_metadata_drafts_only": True,
                        "publishing_instructions_allowed": False,
                        "external_claims_allowed": False,
                        "invented_facts_allowed": False,
                    },
                }
            if self.profile.provider == "openrouter" and self.adapter.adapter_type == "generic_http":
                self._grounding_packet = build_verdict_grounding_packet(context.verdict_record.verdict)
                try:
                    compact_value = self.adapter.generate_json(
                        self._compact_prompt(context, self._grounding_packet),
                        LLM_CREATIVE_BUNDLE_V1_JSON_SCHEMA,
                        self.profile,
                    )
                    compact = LLMCreativeBundleV1.validate(compact_value)
                    self.idea_summary = compact.value["idea_summary"]
                    self.verdict_summary = compact.value["verdict_summary"]
                    self.adapter.provider_diagnostics.compact_schema_valid = True
                    value = normalize_llm_creative_bundle(
                        compact,
                        angle_rubric=ANGLE_RUBRIC,
                        canonical_cta=CTA,
                    )
                    self.adapter.validate_json_schema(value, self._bundle_schema())
                except LLMBundleValidationError as exc:
                    self.adapter.provider_diagnostics.compact_schema_valid = False
                    self.adapter.provider_diagnostics.record_schema_failure("compact_schema_invalid", exc.paths)
                    raise CreativeProviderError("LLM compact creative bundle is invalid") from exc
                except LLMAdapterError as exc:
                    if self.adapter.provider_diagnostics.compact_schema_valid:
                        self.mark_internal_schema_invalid(["$"])
                    elif (
                        self.adapter.provider_diagnostics.content_present
                        and self.adapter.provider_diagnostics.parse_error_type is None
                        and self.adapter.provider_diagnostics.provider_error_type is None
                        and self.adapter.provider_diagnostics.schema_error_type is None
                    ):
                        self.adapter.provider_diagnostics.record_schema_failure(
                            "compact_schema_invalid", ["$"],
                        )
                    raise CreativeProviderError(f"LLM adapter rejected generate_creative_bundle: {exc}") from exc
                except (KeyError, TypeError, ValueError) as exc:
                    self.mark_internal_schema_invalid(["$"])
                    raise CreativeProviderError("LLM compact bundle normalization failed") from exc
            else:
                value = self._call("generate_creative_bundle", payload, self._bundle_schema())
            if not isinstance(value, dict):
                raise CreativeProviderError("online creative bundle is invalid")
            self._bundle = value
        return self._bundle

    @staticmethod
    def _compact_prompt(context: CreativeGenerationContext, grounding_packet: JsonDict) -> str:
        required_ids = "\n".join(f"- {angle_id}" for angle_id in REQUIRED_ANGLE_IDS)
        schema_example = {
            "idea_summary": "...",
            "verdict_summary": "...",
            "cta": "Run your idea through the Ghost Town Test at GhostTownTest.com",
            "angles": [{
                "angle_id": "ghost_town_risk",
                "title": "...",
                "hook": "...",
                "script": "...",
                "caption": "...",
                "thumbnail_text": "...",
                "tags": ["..."],
                "hashtags": ["..."],
            }],
            "longform": {
                "title": "...",
                "intro": "...",
                "chapters": [{"angle_id": "ghost_town_risk", "title": "...", "summary": "..."}],
                "transitions": ["..."],
                "conclusion": "...",
                "description": "...",
            },
        }
        return (
            "Generate a Ghost Town Test creative bundle for this LIT verdict using exactly the compact schema.\n\n"
            "Rules:\n"
            "- exactly five angles\n"
            "- required angle IDs only\n"
            "- include GhostTownTest.com CTA\n"
            "- each hook must match its angle_id\n"
            "- each hook must include a concrete risk, buyer action, or validation mistake\n"
            "- thumbnail_text must be specific to the angle, not generic\n"
            "- every angle hook, script, caption, and thumbnail_text must include a concrete buyer/pain/action signal\n"
            "- buyer: name who has the problem or makes the decision\n"
            "- pain: name the costly mistake, delay, wasted build, missed demand, or invalid assumption\n"
            "- action: name what the builder should test, ask, validate, cut, or decide next\n"
            "- avoid generic startup language\n"
            "- use only the supplied LIT verdict and clearly reflect the specific idea, verdict/risk signal, buyer, painful assumption, and next validation action\n"
            "- No generic hooks.\n"
            "- No generic builder advice.\n"
            "- No external facts.\n"
            "- Every hook must connect to the verdict.\n"
            "- Every script must include buyer + pain + action.\n"
            "- Every thumbnail must be specific to the angle and verdict.\n"
            "- Use only the grounding packet and the supplied LIT verdict.\n"
            "- Do not add industries, platforms, metrics, examples, customer segments, revenue, competitors, geography, market size, timing claims, or external facts unless they appear in the LIT verdict.\n"
            "- If a detail is missing, speak generally using buyer, market, validation test, builder action, idea, risk, or demand signal.\n"
            "- Do not invent specifics.\n"
            "Angle intent:\n"
            "- ghost_town_risk: name the risk of building for people who may not care and include the verdict's market/buyer uncertainty\n"
            "- buyer_reality: confront whether a real buyer would pay, reply, book, switch, or act and name the buyer decision\n"
            "- fast_validation_test: name one fast test before building more and what result would prove interest\n"
            "- contrarian_opportunity: identify the narrow buyer/user/use case where the idea might work and the pain or constraint that makes it real\n"
            "- builder_action_plan: state the next concrete builder action, what to cut/test/ask/validate/decide, and include a buyer or market signal\n"
            "- no external facts beyond the LIT verdict\n"
            "- no publishing instructions\n"
            "- no YouTube API instructions\n"
            "Compact output budget:\n"
            "- exactly 5 angles\n"
            "- hook: max 120 characters\n"
            "- script: max 450 characters\n"
            "- caption: max 180 characters\n"
            "- thumbnail_text: max 36 characters\n"
            "- tags: max 4 items\n"
            "- hashtags: max 4 items\n"
            "- longform.title: max 90 characters\n"
            "- longform.intro: max 250 characters\n"
            "- longform chapter summary: max 160 characters\n"
            "- transitions: max 3 items, max 80 characters each\n"
            "- longform.conclusion: max 220 characters\n"
            "- longform.description: max 300 characters\n"
            "- Return compact JSON. Do not pretty-print. Do not add extra whitespace.\n"
            "- Keep all fields concise. Complete the JSON object before ending.\n"
            "- Return compact JSON only using the LLMCreativeBundleV1 schema.\n\n"
            f"Required angle IDs:\n{required_ids}\n\n"
            f"Compact schema:\n{json.dumps(schema_example, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Grounding packet:\n{json.dumps(grounding_packet, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"LIT verdict:\n{json.dumps(context.verdict_record.verdict, ensure_ascii=False, sort_keys=True)}"
        )

    def _short(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        shorts = self._ensure_bundle(context).get("shorts", {})
        value = shorts.get(angle.get("angle_id")) if isinstance(shorts, dict) else None
        if not isinstance(value, dict):
            raise CreativeProviderError(f"online short is missing for {angle.get('angle_id')}")
        return value

    @staticmethod
    def _bundle_schema() -> JsonDict:
        angle_properties = {
            "angle_id": {"type": "string"},
            "angle_name": {"type": "string"},
            "purpose": {"type": "string"},
            "hook_style": {"type": "string"},
            "target_emotion": {"type": "string"},
            "viewer_question": {"type": "string"},
            "expected_behavior_signal": {"type": "string"},
        }
        metadata_schema = {
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
        }
        short_properties = {
            "title_variants": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "hook": {"type": "string"},
            "script": {"type": "string"},
            "caption": {"type": "string"},
            "thumbnail_text": {"type": "string"},
            "cta": {"type": "string"},
            "youtube_metadata_draft": metadata_schema,
        }
        short_schema = {
            "type": "object",
            "properties": short_properties,
            "required": list(short_properties),
            "additionalProperties": False,
        }
        chapter_schema = {
            "type": "object",
            "properties": {
                "angle_id": {"type": "string"},
                "chapter_title": {"type": "string"},
                "chapter_script": {"type": "string"},
            },
            "required": ["angle_id", "chapter_title", "chapter_script"],
            "additionalProperties": False,
        }
        timestamp_schema = {
            "type": "object",
            "properties": {"timestamp": {"type": "string"}, "label": {"type": "string"}},
            "required": ["timestamp", "label"],
            "additionalProperties": False,
        }
        longform_properties = {
            "longform_title": {"type": "string"},
            "intro_script": {"type": "string"},
            "ordered_chapters": {"type": "array", "items": chapter_schema, "minItems": 5, "maxItems": 5},
            "transition_lines": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4},
            "conclusion": {"type": "string"},
            "cta_to_ghosttowntest_com": {"type": "string"},
            "suggested_description": {"type": "string"},
            "suggested_chapters_timestamps": {
                "type": "array", "items": timestamp_schema, "minItems": 6, "maxItems": 6,
            },
        }
        angle_ids = [row["angle_id"] for row in ANGLE_RUBRIC]
        return {
            "type": "object",
            "properties": {
                "angles": {
                    "type": "array", "minItems": 5, "maxItems": 5,
                    "items": {
                        "type": "object", "properties": angle_properties,
                        "required": list(angle_properties), "additionalProperties": False,
                    },
                },
                "shorts": {
                    "type": "object",
                    "properties": {angle_id: short_schema for angle_id in angle_ids},
                    "required": angle_ids,
                    "additionalProperties": False,
                },
                "longform": {
                    "type": "object", "properties": longform_properties,
                    "required": list(longform_properties), "additionalProperties": False,
                },
            },
            "required": ["angles", "shorts", "longform"],
            "additionalProperties": False,
        }


class SplitOpenRouterCreativeGenerationProvider(OnlineLLMCreativeGenerationProvider):
    """Generate compact creative content one angle at a time across a fallback chain."""

    split_generation_enabled = True
    split_generation_strategy = SPLIT_GENERATION_STRATEGY

    def __init__(
        self,
        profiles: tuple[LLMModelProfile, ...],
        adapter_factory: Callable[[LLMModelProfile], LLMProviderAdapter],
    ) -> None:
        if not profiles or any(profile.provider != "openrouter" for profile in profiles):
            raise CreativeProviderError("split generation requires OpenRouter profiles")
        self.profiles = profiles
        self.adapter_factory = adapter_factory
        self.profile = profiles[0]
        self.model_id = profiles[0].model_id
        self.model_provider = "openrouter"
        self.model_profile_hash = hashlib.sha256(
            "|".join(profile.profile_hash for profile in profiles).encode("utf-8")
        ).hexdigest()
        self.adapter_type = "split_per_angle"
        self._bundle: JsonDict | None = None
        self.idea_summary: str | None = None
        self.verdict_summary: str | None = None
        self._grounding_packet: JsonDict = {}
        self._diagnostics = ProviderContentDiagnostics(
            output_budget_tokens=SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS,
            compact_prompt_budget_enabled=True,
            expected_budget_profile=SPLIT_BUDGET_PROFILE,
        )
        self._adapters: list[LLMProviderAdapter] = []
        self.angle_attempts: list[JsonDict] = []
        self.angle_results: list[JsonDict] = []
        self.angle_ids_completed: list[str] = []
        self.angle_ids_failed: list[str] = []

    @property
    def network_called(self) -> bool:
        return any(adapter.network_called for adapter in self._adapters)

    @property
    def tokens_used(self) -> int | None:
        values = [adapter.tokens_used for adapter in self._adapters if isinstance(adapter.tokens_used, int)]
        return sum(values) if values else None

    @property
    def cost_estimate(self) -> float:
        return round(sum(adapter.estimated_cost for adapter in self._adapters), 8)

    @property
    def estimated_input_tokens(self) -> int:
        return sum(adapter.estimated_input_tokens for adapter in self._adapters)

    @property
    def estimated_output_tokens(self) -> int:
        return sum(adapter.estimated_output_tokens for adapter in self._adapters)

    @property
    def estimated_cost(self) -> float:
        return self.cost_estimate

    @property
    def raw_response_stored(self) -> bool:
        return False

    @property
    def provider_reported_cost(self) -> float | None:
        values = [
            adapter.provider_reported_cost
            for adapter in self._adapters
            if isinstance(adapter.provider_reported_cost, (int, float))
        ]
        return round(sum(values), 8) if values else None

    @property
    def provider_diagnostics(self) -> JsonDict:
        return self._diagnostics.to_dict()

    @property
    def split_generation_metadata(self) -> JsonDict:
        return {
            "split_generation_enabled": True,
            "split_generation_strategy": self.split_generation_strategy,
            "angle_attempt_count": len(self.angle_attempts),
            "angle_success_count": len(self.angle_ids_completed),
            "angle_failure_count": len(self.angle_ids_failed),
            "angle_ids_completed": list(self.angle_ids_completed),
            "angle_ids_failed": list(self.angle_ids_failed),
            "required_angle_ids": list(REQUIRED_ANGLE_IDS),
            "angle_results": [
                {key: deepcopy(value) for key, value in row.items() if not key.startswith("_")}
                for row in self.angle_results
            ],
        }

    def mark_internal_schema_valid(self) -> None:
        self._diagnostics.internal_schema_valid = True
        self._diagnostics.parse_error_type = None
        self._diagnostics.schema_error_type = None
        self._diagnostics.missing_required_fields = []
        self._diagnostics.schema_error_count = 0

    def mark_internal_schema_invalid(self, paths: list[str] | None = None) -> None:
        self._diagnostics.internal_schema_valid = False
        self._diagnostics.record_schema_failure("internal_schema_invalid", paths or ["$"])

    def mark_quality_result(
        self,
        *,
        quality_valid: bool,
        gates: tuple[JsonDict, ...],
        required_angle_ids: list[str],
        angle_ids: list[str],
        short_summaries: list[JsonDict],
        longform_present: bool,
        longform_cta_present: bool,
        longform_ghosttowntest_cta_present: bool,
    ) -> None:
        self._diagnostics.record_grounding_packet(self._grounding_packet)
        self._diagnostics.record_quality_result(
            quality_valid=quality_valid,
            gates=gates,
            required_angle_ids=required_angle_ids,
            angle_ids=angle_ids,
            short_summaries=short_summaries,
            longform_present=longform_present,
            longform_cta_present=longform_cta_present,
            longform_ghosttowntest_cta_present=longform_ghosttowntest_cta_present,
        )

    def mark_quality_invalid(self, **kwargs: Any) -> None:
        self.mark_quality_result(quality_valid=False, **kwargs)

    def _ensure_bundle(self, context: CreativeGenerationContext) -> JsonDict:
        if self._bundle is not None:
            return self._bundle
        self._grounding_packet = build_verdict_grounding_packet(context.verdict_record.verdict)
        accepted: list[JsonDict] = []
        for angle_id in REQUIRED_ANGLE_IDS:
            accepted_angle = self._generate_angle_with_fallback(context, angle_id)
            if accepted_angle is None:
                self.angle_ids_failed.append(angle_id)
            else:
                self.angle_ids_completed.append(angle_id)
                accepted.append(accepted_angle)
        if self.angle_ids_failed:
            failed_results = [row for row in self.angle_results if row["angle_status"] == "blocked"]
            best_failure = max(failed_results, key=lambda row: self._stage_rank(row["stage_reached"]))
            self._diagnostics = ProviderContentDiagnostics(**deepcopy(best_failure["_provider_diagnostics"]))
            self._diagnostics.compact_schema_valid = False
            self._diagnostics.internal_schema_valid = False
            self._diagnostics.final_block_reason = best_failure["final_block_reason"]
            raise CreativeProviderError("one or more required split-generation angles failed")

        compact_value = self._assemble_compact_bundle(context, accepted)
        try:
            compact = LLMCreativeBundleV1.validate(compact_value)
            value = normalize_llm_creative_bundle(compact, angle_rubric=ANGLE_RUBRIC, canonical_cta=CTA)
            LLMProviderAdapter.validate_json_schema(value, self._bundle_schema())
        except LLMBundleValidationError as exc:
            self._diagnostics.compact_schema_valid = False
            self._diagnostics.record_schema_failure("compact_schema_invalid", exc.paths)
            raise CreativeProviderError("assembled split creative bundle is invalid") from exc
        except LLMAdapterError as exc:
            self.mark_internal_schema_invalid(["$"])
            raise CreativeProviderError("assembled split creative bundle failed internal schema") from exc
        self.idea_summary = compact.value["idea_summary"]
        self.verdict_summary = compact.value["verdict_summary"]
        last_success = self.angle_attempts[-1]["provider_diagnostics"]
        self._diagnostics = ProviderContentDiagnostics(**deepcopy(last_success))
        self._diagnostics.compact_schema_valid = True
        self._diagnostics.internal_schema_valid = False
        self._diagnostics.output_budget_tokens = SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS
        self._diagnostics.compact_prompt_budget_enabled = True
        self._diagnostics.expected_budget_profile = SPLIT_BUDGET_PROFILE
        self._diagnostics.record_grounding_packet(self._grounding_packet)
        self._bundle = value
        return value

    def _generate_angle_with_fallback(
        self, context: CreativeGenerationContext, angle_id: str,
    ) -> JsonDict | None:
        attempts: list[JsonDict] = []
        accepted: JsonDict | None = None
        for profile in self.profiles:
            diagnostics = ProviderContentDiagnostics(
                provider_selected_model=profile.provider_model,
                provider_selected_provider=profile.provider,
                output_budget_tokens=SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS,
                compact_prompt_budget_enabled=True,
                expected_budget_profile=SPLIT_BUDGET_PROFILE,
            )
            adapter: LLMProviderAdapter | None = None
            try:
                adapter = self.adapter_factory(profile)
                self._adapters.append(adapter)
                value = adapter.generate_json_with_budget(
                    self._angle_prompt(context, self._grounding_packet, angle_id),
                    LLM_CREATIVE_ANGLE_V1_JSON_SCHEMA,
                    profile,
                    output_budget_tokens=SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS,
                    expected_budget_profile=SPLIT_BUDGET_PROFILE,
                )
                diagnostics = adapter.provider_diagnostics
                diagnostics.output_budget_tokens = SINGLE_ANGLE_OUTPUT_BUDGET_TOKENS
                diagnostics.compact_prompt_budget_enabled = True
                diagnostics.expected_budget_profile = SPLIT_BUDGET_PROFILE
                angle = LLMCreativeAngleV1.validate(value, expected_angle_id=angle_id)
                diagnostics.compact_schema_valid = True
                self._record_angle_quality(diagnostics, angle.value, context)
                if not diagnostics.quality_valid:
                    raise CreativeProviderError("split angle failed quality validation")
                accepted = angle.to_dict()
            except LLMBundleValidationError as exc:
                if adapter is not None:
                    diagnostics = adapter.provider_diagnostics
                diagnostics.compact_schema_valid = False
                diagnostics.record_schema_failure("compact_schema_invalid", exc.paths)
            except (LLMAdapterError, CreativeProviderError):
                if adapter is not None:
                    diagnostics = adapter.provider_diagnostics
                if (
                    diagnostics.content_present
                    and diagnostics.parse_error_type is None
                    and diagnostics.provider_error_type is None
                    and diagnostics.schema_error_type is None
                    and not diagnostics.quality_error_type
                ):
                    diagnostics.record_schema_failure("compact_schema_invalid", ["$"])
            stage = "passed" if accepted is not None else self._diagnostic_stage(diagnostics)
            attempt = self._safe_angle_attempt(
                angle_id=angle_id,
                profile=profile,
                angle_attempt_number=len(attempts) + 1,
                diagnostics=diagnostics,
                stage=stage,
                adapter=adapter,
            )
            attempts.append(attempt)
            self.angle_attempts.append(attempt)
            if accepted is not None:
                self.model_id = profile.model_id
                break
        selected = attempts[-1] if accepted is not None else max(
            attempts, key=lambda row: self._stage_rank(row["stage_reached"]),
        )
        self.angle_results.append({
            "angle_id": angle_id,
            "angle_attempt_count": len(attempts),
            "angle_status": "passed" if accepted is not None else "blocked",
            "stage_reached": selected["stage_reached"],
            "final_block_reason": selected["final_block_reason"],
            "provider_selected_model": selected["provider_diagnostics"].get("provider_selected_model"),
            "provider_selected_provider": selected["provider_diagnostics"].get("provider_selected_provider"),
            "provider_http_status": selected["provider_diagnostics"].get("provider_http_status"),
            "content_present": selected["provider_diagnostics"].get("content_present", False),
            "content_length": selected["provider_diagnostics"].get("content_length", 0),
            "parse_error_type": selected["provider_diagnostics"].get("parse_error_type"),
            "json_parse_error_type": selected["provider_diagnostics"].get("json_parse_error_type"),
            "likely_truncated": selected["provider_diagnostics"].get("likely_truncated", False),
            "truncation_risk_detected": selected["provider_diagnostics"].get("truncation_risk_detected", False),
            "compact_schema_valid": selected["provider_diagnostics"].get("compact_schema_valid", False),
            "angle_quality_valid": selected["provider_diagnostics"].get("quality_valid", False),
            "quality_error_type": selected["provider_diagnostics"].get("quality_error_type"),
            "quality_failed_checks": selected["provider_diagnostics"].get("quality_failed_checks", []),
            "output_budget_tokens": selected["provider_diagnostics"].get("output_budget_tokens", 0),
            "expected_budget_profile": selected["provider_diagnostics"].get("expected_budget_profile"),
            "_provider_diagnostics": deepcopy(selected["provider_diagnostics"]),
        })
        return accepted

    def _record_angle_quality(
        self, diagnostics: ProviderContentDiagnostics, angle: JsonDict, context: CreativeGenerationContext,
    ) -> None:
        from .creative_angle_gates import (
            buyer_pain_action_signals,
            hook_specificity_signals,
            verdict_grounding_signals,
        )

        job = SimpleNamespace(
            angle_id=angle["angle_id"],
            hook=angle["hook"],
            script=angle["script"],
            caption=angle["caption"],
            thumbnail_text=angle["thumbnail_text"],
            cta=CTA,
        )
        buyer = buyer_pain_action_signals(job)
        verdict = verdict_grounding_signals(job, context.verdict_record.verdict, self._grounding_packet)
        hook = hook_specificity_signals(job, context.verdict_record.verdict)
        checks = {
            "specific_hooks": not (
                hook["hook_generic"] or not hook["hook_angle_match"] or not hook["hook_verdict_signal_present"]
            ),
            "buyer_pain_action_specificity": all(buyer.values()),
            "verdict_grounded_claims": (
                verdict["verdict_signal_present"]
                and not verdict["generic_claim_signal_present"]
                and not verdict["external_fact_signal_present"]
                and verdict["idea_specificity_present"]
                and verdict["angle_specificity_present"]
            ),
            "thumbnail_specificity": 3 <= len(angle["thumbnail_text"].split()) and len(angle["thumbnail_text"]) <= 36,
        }
        gates = [
            {"gate_name": name, "status": "pass" if passed else "fail", "blocking": not passed}
            for name, passed in checks.items()
        ]
        summary = {
            "angle_id": angle["angle_id"],
            "script_present": True,
            "caption_present": True,
            "thumbnail_text_present": True,
            "hashtags_present": bool(angle["hashtags"]),
            "cta_present": True,
            "ghosttowntest_cta_present": True,
            **buyer,
            **verdict,
            **hook,
        }
        diagnostics.record_grounding_packet(self._grounding_packet)
        diagnostics.record_quality_result(
            quality_valid=all(checks.values()),
            gates=gates,
            required_angle_ids=[angle["angle_id"]],
            angle_ids=[angle["angle_id"]],
            short_summaries=[summary],
            longform_present=True,
            longform_cta_present=True,
            longform_ghosttowntest_cta_present=True,
        )

    @staticmethod
    def _safe_angle_attempt(
        *, angle_id: str, profile: LLMModelProfile, angle_attempt_number: int,
        diagnostics: ProviderContentDiagnostics, stage: str, adapter: LLMProviderAdapter | None,
    ) -> JsonDict:
        safe = diagnostics.to_dict()
        return {
            "attempt_number": 0,
            "angle_attempt_number": angle_attempt_number,
            "angle_id": angle_id,
            "model_id": profile.model_id,
            "provider_model": profile.provider_model,
            "status": "passed" if stage == "passed" else "blocked",
            "schema_valid": stage == "passed",
            "quality_valid": safe.get("quality_valid", False),
            "stage_reached": stage,
            "final_block_reason": None if stage == "passed" else stage,
            "tokens_used": adapter.tokens_used if adapter is not None else None,
            "cost_estimate": adapter.estimated_cost if adapter is not None else None,
            "provider_reported_cost": adapter.provider_reported_cost if adapter is not None else None,
            "network_called": adapter.network_called if adapter is not None else False,
            "publish_attempted": False,
            "youtube_api_called": False,
            "videos_insert_called": False,
            "full_autopilot_enabled": False,
            "supervised_autopilot_enabled": False,
            "live_publishing_enabled": False,
            "secrets_recorded": False,
            "raw_response_stored": False,
            "reasoning_details_stored": False,
            "stream_enabled": False,
            "provider_diagnostics": safe,
        }

    @staticmethod
    def _stage_rank(stage: str) -> int:
        return {
            "network_failed": 0,
            "provider_rate_limited": 1,
            "empty_provider_content": 2,
            "malformed_json": 3,
            "compact_schema_invalid": 4,
            "quality_invalid": 6,
            "passed": 7,
        }.get(stage, -1)

    @staticmethod
    def _diagnostic_stage(diagnostics: ProviderContentDiagnostics) -> str:
        if diagnostics.quality_error_type or diagnostics.final_block_reason == "quality_invalid":
            return "quality_invalid"
        if diagnostics.schema_error_type == "compact_schema_invalid":
            return "compact_schema_invalid"
        if diagnostics.provider_error_type == "rate_limited":
            return "provider_rate_limited"
        if diagnostics.parse_error_type == "empty_provider_content":
            return "empty_provider_content"
        if diagnostics.parse_error_type in {"malformed_json", "json_object_not_found", "unsafe_provider_content"}:
            return "malformed_json"
        return "network_failed"

    @staticmethod
    def _assemble_compact_bundle(
        context: CreativeGenerationContext, angles: list[JsonDict],
    ) -> JsonDict:
        idea_label = _clip(_clean(context.idea.name, "Business idea"), 90)
        verdict_text = _clip(
            _clean(context.verdict_record.verdict.get("summary"), "Review the stored LIT verdict before building"),
            180,
        )
        chapters = [
            {
                "angle_id": angle["angle_id"],
                "title": _clip(angle["title"], 90),
                "summary": _clip(angle["script"], 160),
            }
            for angle in angles
        ]
        return {
            "idea_summary": idea_label,
            "verdict_summary": verdict_text,
            "cta": CTA,
            "angles": deepcopy(angles),
            "longform": {
                "title": _clip(f"Ghost Town Test: {idea_label}", 90),
                "intro": _clip(f"Use the stored Ghost Town Test verdict to examine {idea_label}.", 250),
                "chapters": chapters,
                "transitions": [
                    "Next, compare this angle with the same buyer evidence.",
                    "Now test the next assumption against the stored verdict.",
                    "Then narrow the opportunity using the same demand signal.",
                    "Finally, turn the evidence into one builder action.",
                ],
                "conclusion": _clip(f"Use the evidence before building more. {CTA}", 220),
                "description": _clip(f"Five verdict-grounded validation angles for {idea_label}. {CTA}", 300),
            },
        }

    @staticmethod
    def _angle_prompt(
        context: CreativeGenerationContext, grounding_packet: JsonDict, angle_id: str,
    ) -> str:
        intent = {
            "ghost_town_risk": "Name the risk of building for people who may not care and the verdict's buyer or market uncertainty.",
            "buyer_reality": "Confront whether a real buyer would pay, reply, book, switch, decide, or act.",
            "fast_validation_test": "Name one fast test before building and the result that would prove interest.",
            "contrarian_opportunity": "Identify a narrow buyer, user, or use case and the pain or constraint that makes it real.",
            "builder_action_plan": "State what to cut, test, ask, validate, or decide next using a buyer or market signal.",
        }[angle_id]
        schema_example = {
            "angle_id": angle_id,
            "title": "...",
            "hook": "...",
            "script": "...",
            "caption": "...",
            "thumbnail_text": "...",
            "tags": ["..."],
            "hashtags": ["..."],
        }
        return (
            f"Generate exactly one compact creative angle JSON object for target angle_id: {angle_id}.\n\n"
            "Rules:\n"
            f"- angle_id must be exactly {angle_id}\n"
            f"- angle-specific intent: {intent}\n"
            "- use only the supplied LIT verdict and grounding packet\n"
            "- do not invent buyer segments, platforms, channels, metrics, revenue, competitors, market size, or outcomes\n"
            "- no external facts\n"
            "- if details are absent, use generic safe terms: buyer, market, validation test, builder action, idea, risk, demand signal\n"
            "- hook must be specific to the target angle and include a verdict signal\n"
            "- hook and script must include a buyer, pain or risk, and concrete action\n"
            "- thumbnail_text must be specific to the angle and verdict\n"
            f"- canonical CTA for code-owned final assembly: {CTA}\n"
            "- do not repeat the CTA in this angle object\n"
            "- hook: max 120 characters\n"
            "- script: max 450 characters\n"
            "- caption: max 180 characters\n"
            "- thumbnail_text: max 36 characters\n"
            "- tags: max 4 items\n"
            "- hashtags: max 4 items\n"
            "- Return exactly one valid JSON object.\n"
            "- Return compact JSON.\n"
            "- No pretty printing.\n"
            "- No markdown.\n"
            "- No explanation.\n"
            "- No comments.\n"
            "- No trailing commas.\n"
            "- No extra text before or after JSON.\n"
            "- Complete the JSON object before ending.\n\n"
            f"Single-angle schema:\n{json.dumps(schema_example, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Grounding packet:\n{json.dumps(grounding_packet, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"LIT verdict:\n{json.dumps(context.verdict_record.verdict, ensure_ascii=False, sort_keys=True)}"
        )
