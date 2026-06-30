from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .autopilot_models import BusinessIdeaCandidate, VerdictRecord


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class CreativeGenerationContext:
    idea: BusinessIdeaCandidate
    verdict_record: VerdictRecord
    lit_verdict_id: str
    source_receipt_references: dict[str, str]

    def provider_input(self) -> JsonDict:
        return {
            "idea": self.idea.to_dict(),
            "lit_verdict_id": self.lit_verdict_id,
            "verdict": self.verdict_record.verdict,
        }


class CreativeGenerationProvider(ABC):
    provider_type: str
    model_id: str | None = None
    prompt_prefix: str = ""
    network_called: bool = False
    tokens_used: int | None = None
    cost_estimate: float | None = None

    @abstractmethod
    def generate_angle_pack(self, context: CreativeGenerationContext) -> list[JsonDict]:
        raise NotImplementedError

    @abstractmethod
    def generate_short_script(self, context: CreativeGenerationContext, angle: JsonDict) -> JsonDict:
        raise NotImplementedError

    @abstractmethod
    def generate_title_variants(self, context: CreativeGenerationContext, angle: JsonDict) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def generate_thumbnail_text(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_caption(self, context: CreativeGenerationContext, angle: JsonDict) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_youtube_metadata_draft(
        self,
        context: CreativeGenerationContext,
        angle: JsonDict,
        short_content: JsonDict,
    ) -> JsonDict:
        raise NotImplementedError

    @abstractmethod
    def generate_longform_assembly_plan(
        self,
        context: CreativeGenerationContext,
        short_jobs: list[JsonDict],
    ) -> JsonDict:
        raise NotImplementedError
