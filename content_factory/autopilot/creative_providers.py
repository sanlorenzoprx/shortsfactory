from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .creative_generation_provider import CreativeGenerationContext, CreativeGenerationProvider, JsonDict


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


@dataclass(frozen=True)
class OnlineLLMConfig:
    api_url: str
    api_key: str
    model_id: str
    timeout_seconds: float = 45.0

    @classmethod
    def load(
        cls,
        *,
        model_override: str | None = None,
        config_path: str | Path = ".local/creative_llm/config.json",
    ) -> "OnlineLLMConfig":
        local: JsonDict = {}
        path = Path(config_path).expanduser()
        if path.is_file():
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CreativeProviderError("online LLM local config is invalid") from exc
            if isinstance(parsed, dict):
                local = parsed
        api_url = os.getenv("CREATIVE_LLM_API_URL", str(local.get("api_url", ""))).strip()
        api_key = os.getenv("CREATIVE_LLM_API_KEY", str(local.get("api_key", ""))).strip()
        model_id = (model_override or os.getenv("CREATIVE_LLM_MODEL") or str(local.get("model_id", ""))).strip()
        timeout_raw = os.getenv("CREATIVE_LLM_TIMEOUT_SECONDS", str(local.get("timeout_seconds", 45)))
        if not api_url or not api_key or not model_id:
            raise CreativeProviderError(
                "online_llm requires CREATIVE_LLM_API_URL, CREATIVE_LLM_API_KEY, and --model/CREATIVE_LLM_MODEL"
            )
        parsed_url = urlparse(api_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or parsed_url.username or parsed_url.password:
            raise CreativeProviderError("CREATIVE_LLM_API_URL must be a safe HTTP(S) endpoint")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise CreativeProviderError("CREATIVE_LLM_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise CreativeProviderError("CREATIVE_LLM_TIMEOUT_SECONDS must be positive")
        return cls(api_url=api_url, api_key=api_key, model_id=model_id, timeout_seconds=timeout)


class OnlineLLMCreativeGenerationProvider(CreativeGenerationProvider):
    provider_type = "online_llm"
    prompt_prefix = PROMPT_PREFIX

    def __init__(
        self,
        config: OnlineLLMConfig,
        *,
        transport: Callable[..., Any] | None = None,
    ):
        self.config = config
        self.model_id = config.model_id
        self.network_called = False
        self.tokens_used = None
        self.cost_estimate = None
        self._transport = transport

    def _call(self, task: str, payload: JsonDict) -> Any:
        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": self.prompt_prefix},
                {"role": "user", "content": json.dumps({"task": task, "input": payload}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        self.network_called = True
        try:
            if self._transport is None:
                import requests

                response = requests.post(
                    self.config.api_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=self.config.timeout_seconds,
                )
            else:
                response = self._transport(
                    url=self.config.api_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=self.config.timeout_seconds,
                )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            raw = response.json() if hasattr(response, "json") else response
            value = self._structured_value(raw)
            usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
            if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                self.tokens_used = (self.tokens_used or 0) + usage["total_tokens"]
            cost = raw.get("cost_estimate") if isinstance(raw, dict) else None
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                self.cost_estimate = round((self.cost_estimate or 0.0) + float(cost), 8)
            return value
        except CreativeProviderError:
            raise
        except Exception as exc:
            raise CreativeProviderError(f"online LLM request failed: {type(exc).__name__}") from exc

    @staticmethod
    def _structured_value(raw: Any) -> Any:
        if not isinstance(raw, dict):
            raise CreativeProviderError("online LLM response is not a JSON object")
        value: Any = raw.get("result", raw.get("output"))
        if value is None:
            choices = raw.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message", {})
                value = message.get("content") if isinstance(message, dict) else None
        if value is None and isinstance(raw.get("output_text"), str):
            value = raw["output_text"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CreativeProviderError("online LLM did not return structured JSON") from exc
        if value is None:
            raise CreativeProviderError("online LLM response has no structured output")
        return value

    def generate_angle_pack(self, context: CreativeGenerationContext) -> list[JsonDict]:
        value = self._call("generate_angle_pack", {**context.provider_input(), "required_angles": list(ANGLE_RUBRIC)})
        angles = value.get("angles") if isinstance(value, dict) else value
        if not isinstance(angles, list):
            raise CreativeProviderError("online angle pack is invalid")
        return angles

    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        value = self._call("generate_short_script", {**context.provider_input(), "angle": angle, "required_cta": CTA})
        if not isinstance(value, dict):
            raise CreativeProviderError("online short script is invalid")
        return value

    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        value = self._call("generate_title_variants", {**context.provider_input(), "angle": angle, "max_length": 100})
        variants = value.get("title_variants") if isinstance(value, dict) else value
        if not isinstance(variants, list):
            raise CreativeProviderError("online title variants are invalid")
        return variants

    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        value = self._call("generate_thumbnail_text", {**context.provider_input(), "angle": angle})
        return str(value.get("thumbnail_text", "")) if isinstance(value, dict) else str(value)

    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        value = self._call("generate_caption", {**context.provider_input(), "angle": angle, "required_cta": CTA})
        return str(value.get("caption", "")) if isinstance(value, dict) else str(value)

    def generate_youtube_metadata_draft(
        self, context: CreativeGenerationContext, angle: JsonDict, short_content: JsonDict,
    ) -> JsonDict:
        value = self._call(
            "generate_youtube_metadata_draft",
            {**context.provider_input(), "angle": angle, "short": short_content, "status": "draft_not_upload_ready"},
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
        )
        if not isinstance(value, dict):
            raise CreativeProviderError("online long-form plan is invalid")
        return value
