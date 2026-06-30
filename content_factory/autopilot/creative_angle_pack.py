from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .autopilot_models import BusinessIdeaCandidate, VerdictRecord
from .autopilot_store import AutopilotStore, AutopilotStoreError
from .creative_angle_gates import CreativeGateError, assert_safe_provider_input, evaluate_creative_pack
from .creative_angle_models import (
    AngleShortJob,
    CreativeAngleContractError,
    CreativeAnglePack,
    CreativeAnglePackReceipt,
    CreativeAngleSpec,
    LongFormAssemblyPlan,
)
from .creative_generation_provider import CreativeGenerationContext, CreativeGenerationProvider
from .creative_providers import (
    RUBRIC_VERSION,
    CreativeProviderError,
    DeterministicCreativeGenerationProvider,
    FixtureCreativeGenerationProvider,
    OnlineLLMConfig,
    OnlineLLMCreativeGenerationProvider,
)


RECEIPT_VERSION = "phase5b.5.creative-angle-pack.v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class CreativeAnglePackError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _short_hash(value: Any) -> str:
    return _sha256(value)[:12]


def _atomic_json(path: Path, value: Any) -> None:
    encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".creative-angle.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_text(path: Path, value: str) -> None:
    encoded = value.rstrip().encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".creative-angle.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_lit_verdict_fixture(path: str | Path) -> tuple[BusinessIdeaCandidate, VerdictRecord, dict[str, Any]]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.is_file():
        raise CreativeAnglePackError(f"LIT verdict fixture is missing: {fixture_path.name}")
    try:
        value = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CreativeAnglePackError("LIT verdict fixture is invalid JSON") from exc
    if not isinstance(value, dict):
        raise CreativeAnglePackError("LIT verdict fixture must contain a JSON object")
    idea_value = value.get("idea")
    if not isinstance(idea_value, dict):
        raise CreativeAnglePackError("LIT verdict fixture is missing idea")
    if "idea_id" not in idea_value:
        nested_name = str(idea_value.get("name", "Fixture Business Idea"))
        idea_value = {
            "idea_id": str(value.get("idea_id") or f"idea_fixture_{_short_hash(nested_name)}"),
            "source_trend_id": str(value.get("trend_id") or "trend_fixture"),
            "name": nested_name,
            "description": str(idea_value.get("description", "")),
            "target_user": str(idea_value.get("target_user", "target buyer")),
            "market": str(idea_value.get("market", "US")),
            "locale": str(value.get("locale", "en-US")),
            "angle": str(value.get("angle", "fixture validation angle")),
            "why_now": str(value.get("why_now", "Fixture evidence is stored for offline regression testing.")),
            "constraints": list(value.get("constraints", ["validate willingness to pay before building"])),
            "created_at": str(value.get("created_at", "2026-06-30T00:00:00+00:00")),
        }
    record_value = value.get("verdict_record")
    if isinstance(record_value, dict):
        verdict_record = VerdictRecord.from_dict(record_value)
    else:
        verdict = value.get("verdict")
        if not isinstance(verdict, dict):
            raise CreativeAnglePackError("LIT verdict fixture is missing verdict")
        verdict_record = VerdictRecord(
            idea_id=str(idea_value["idea_id"]),
            verdict=verdict,
            warning=None,
            created_at=str(value.get("created_at", "2026-06-30T00:00:00+00:00")),
        )
    return BusinessIdeaCandidate.from_dict(idea_value), verdict_record, value


class CreativeAnglePackGenerator:
    def __init__(
        self,
        *,
        provider: CreativeGenerationProvider | None = None,
        output_root: str | Path = "output",
        now: Callable[[], datetime] = _utc_now,
        online_provider_explicit: bool = False,
    ):
        self.provider = provider or DeterministicCreativeGenerationProvider()
        self.output_root = Path(output_root).expanduser().resolve()
        self.store = AutopilotStore(self.output_root)
        self.now = now
        self.online_provider_explicit = online_provider_explicit

    def generate(
        self,
        *,
        idea_id: str | None = None,
        batch_id: str | None = None,
        lit_verdict_file: str | Path | None = None,
    ) -> CreativeAnglePackReceipt:
        if lit_verdict_file is not None:
            idea, verdict_record, _ = load_lit_verdict_fixture(lit_verdict_file)
            source_references = {"lit_verdict_fixture": self._safe_external_reference(Path(lit_verdict_file))}
            source_batch = "fixture"
        else:
            if idea_id is None:
                raise CreativeAnglePackError("idea_id or lit_verdict_file is required")
            self._validate_id(idea_id, "idea_id")
            if batch_id is not None:
                self._validate_id(batch_id, "batch_id")
            source_batch, idea, verdict_record = self._find_source(idea_id, batch_id)
            source_references = self._source_references(source_batch)
        return self.generate_from_records(
            idea=idea,
            verdict_record=verdict_record,
            batch_id=source_batch,
            source_receipt_references=source_references,
        )

    def generate_from_records(
        self,
        *,
        idea: BusinessIdeaCandidate,
        verdict_record: VerdictRecord,
        batch_id: str,
        source_receipt_references: dict[str, str],
    ) -> CreativeAnglePackReceipt:
        if verdict_record.idea_id != idea.idea_id:
            raise CreativeAnglePackError("idea and LIT verdict do not match")
        self._validate_verdict(verdict_record.verdict)
        timestamp = self.now().astimezone(timezone.utc).isoformat()
        lit_verdict_id = f"litv_{_short_hash({'idea_id': idea.idea_id, 'verdict': verdict_record.verdict})}"
        provider_input = {
            "idea": idea.to_dict(),
            "lit_verdict_id": lit_verdict_id,
            "verdict": verdict_record.verdict,
        }
        assert_safe_provider_input(provider_input)
        input_hash = _sha256(provider_input)
        prompt_prefix_hash = hashlib.sha256(self.provider.prompt_prefix.encode("utf-8")).hexdigest()
        angle_pack_id = f"cap_{_short_hash({'input_hash': input_hash, 'provider': self.provider.provider_type, 'model': self.provider.model_id, 'timestamp': timestamp})}"
        context = CreativeGenerationContext(
            idea=idea,
            verdict_record=verdict_record,
            lit_verdict_id=lit_verdict_id,
            source_receipt_references=source_receipt_references,
        )
        raw_output: dict[str, Any] = {}
        if self.provider.provider_type == "online_llm" and not self.online_provider_explicit:
            return self._write_receipt(
                timestamp=timestamp,
                angle_pack_id=angle_pack_id,
                prompt_prefix_hash=prompt_prefix_hash,
                input_hash=input_hash,
                output_hash=_sha256(raw_output),
                gates=({
                    "gate_name": "online_provider_explicit",
                    "status": "fail",
                    "blocking": True,
                    "reason": "online provider use requires an explicit provider flag",
                },),
                source_receipt_references=source_receipt_references,
                status="blocked",
                five_angles_generated=False,
                short_jobs_created=0,
                longform_plan_created=False,
                artifacts={},
            )
        try:
            raw_angles = self.provider.generate_angle_pack(context)
            raw_output["angles"] = raw_angles
            angles = tuple(CreativeAngleSpec.from_dict(value) for value in raw_angles)
            short_jobs, raw_shorts = self._build_shorts(context, angles, angle_pack_id)
            raw_output["shorts"] = raw_shorts
            raw_longform = self.provider.generate_longform_assembly_plan(
                context, [job.to_dict() for job in short_jobs],
            )
            raw_output["longform"] = raw_longform
            output_hash = _sha256(raw_output)
            pack = CreativeAnglePack(
                angle_pack_id=angle_pack_id,
                idea_id=idea.idea_id,
                trend_id=idea.source_trend_id or None,
                lit_verdict_id=lit_verdict_id,
                rubric_version=RUBRIC_VERSION,
                provider_type=self.provider.provider_type,
                model_id=self.provider.model_id,
                prompt_prefix_hash=prompt_prefix_hash,
                input_hash=input_hash,
                output_hash=output_hash,
                angles=angles,
            )
            longform = self._build_longform(raw_longform, short_jobs, angle_pack_id)
            gates = evaluate_creative_pack(
                pack=pack,
                short_jobs=short_jobs,
                longform=longform,
                source_verdict=verdict_record.verdict,
                online_provider_explicit=self.online_provider_explicit,
            )
        except (CreativeAngleContractError, CreativeProviderError, KeyError, TypeError, ValueError) as exc:
            output_hash = _sha256(raw_output)
            gates = ({
                "gate_name": "provider_schema_validation",
                "status": "fail",
                "blocking": True,
                "reason": f"provider output failed schema validation ({type(exc).__name__})",
            },)
            return self._write_receipt(
                timestamp=timestamp,
                angle_pack_id=angle_pack_id,
                prompt_prefix_hash=prompt_prefix_hash,
                input_hash=input_hash,
                output_hash=output_hash,
                gates=gates,
                source_receipt_references=source_receipt_references,
                status="blocked",
                five_angles_generated=len(raw_output.get("angles", [])) == 5,
                short_jobs_created=0,
                longform_plan_created=False,
                artifacts={},
            )
        if any(gate["blocking"] for gate in gates):
            return self._write_receipt(
                timestamp=timestamp,
                angle_pack_id=angle_pack_id,
                prompt_prefix_hash=prompt_prefix_hash,
                input_hash=input_hash,
                output_hash=output_hash,
                gates=gates,
                source_receipt_references=source_receipt_references,
                status="blocked",
                five_angles_generated=True,
                short_jobs_created=0,
                longform_plan_created=False,
                artifacts={},
            )
        artifacts = self._persist_artifacts(pack, short_jobs, longform)
        return self._write_receipt(
            timestamp=timestamp,
            angle_pack_id=angle_pack_id,
            prompt_prefix_hash=prompt_prefix_hash,
            input_hash=input_hash,
            output_hash=output_hash,
            gates=gates,
            source_receipt_references=source_receipt_references,
            status="completed",
            five_angles_generated=True,
            short_jobs_created=5,
            longform_plan_created=True,
            artifacts=artifacts,
        )

    def _build_shorts(
        self,
        context: CreativeGenerationContext,
        angles: tuple[CreativeAngleSpec, ...],
        angle_pack_id: str,
    ) -> tuple[tuple[AngleShortJob, ...], list[dict[str, Any]]]:
        jobs = []
        raw_shorts = []
        for angle_model in angles:
            angle = angle_model.to_dict()
            script_value = self.provider.generate_short_script(context, angle)
            title_variants = self.provider.generate_title_variants(context, angle)
            thumbnail_text = self.provider.generate_thumbnail_text(context, angle)
            caption = self.provider.generate_caption(context, angle)
            if not isinstance(script_value, dict) or not isinstance(title_variants, list) or not title_variants:
                raise CreativeProviderError(f"provider short output is incomplete for {angle_model.angle_id}")
            title = str(title_variants[0])
            tags = ("business ideas", "startup validation", "ghost town test", angle_model.angle_id.replace("_", " "))
            hashtags = ("#BusinessIdeas", "#StartupValidation", "#GhostTownTest", "#Shorts")
            short_content = {
                "title": title,
                "hook": str(script_value.get("hook", "")),
                "script": str(script_value.get("script", "")),
                "caption": str(caption),
                "thumbnail_text": str(thumbnail_text),
                "cta": str(script_value.get("cta", "")),
                "tags": tags,
                "hashtags": hashtags,
            }
            metadata = self.provider.generate_youtube_metadata_draft(context, angle, short_content)
            if not isinstance(metadata, dict):
                raise CreativeProviderError(f"provider metadata is invalid for {angle_model.angle_id}")
            job_id = f"asj_{_short_hash({'angle_pack_id': angle_pack_id, 'angle_id': angle_model.angle_id})}"
            metadata = dict(metadata)
            metadata.setdefault("schema_version", "youtube_metadata_draft.v1")
            metadata.setdefault("platform", "youtube_shorts")
            metadata.setdefault("source_job_id", job_id)
            metadata.setdefault("idea_id", context.idea.idea_id)
            metadata.setdefault("lit_verdict_id", context.lit_verdict_id)
            metadata.setdefault("angle_id", angle_model.angle_id)
            metadata.setdefault("cta", short_content["cta"])
            metadata.setdefault("tags", list(tags))
            metadata.setdefault("hashtags", list(hashtags))
            metadata.setdefault("status", "draft_not_upload_ready")
            metadata.setdefault("live_publish_enabled", False)
            metadata["source_receipt_references"] = context.source_receipt_references
            job = AngleShortJob(
                job_id=job_id,
                angle_pack_id=angle_pack_id,
                angle_id=angle_model.angle_id,
                idea_id=context.idea.idea_id,
                lit_verdict_id=context.lit_verdict_id,
                title=short_content["title"],
                hook=short_content["hook"],
                script=short_content["script"],
                caption=short_content["caption"],
                thumbnail_text=short_content["thumbnail_text"],
                cta=short_content["cta"],
                tags=tags,
                hashtags=hashtags,
                youtube_metadata_draft=metadata,
                source_receipt_references=context.source_receipt_references,
            )
            jobs.append(job)
            raw_shorts.append({
                "angle_id": angle_model.angle_id,
                "script": script_value,
                "title_variants": title_variants,
                "thumbnail_text": thumbnail_text,
                "caption": caption,
                "youtube_metadata_draft": metadata,
            })
        return tuple(jobs), raw_shorts

    @staticmethod
    def _build_longform(
        raw: dict[str, Any], short_jobs: tuple[AngleShortJob, ...], angle_pack_id: str,
    ) -> LongFormAssemblyPlan:
        return LongFormAssemblyPlan(
            longform_id=f"lfp_{_short_hash({'angle_pack_id': angle_pack_id})}",
            angle_pack_id=angle_pack_id,
            longform_title=str(raw.get("longform_title", "")),
            intro_script=str(raw.get("intro_script", "")),
            ordered_chapters=tuple(raw.get("ordered_chapters", [])),
            transition_lines=tuple(raw.get("transition_lines", [])),
            conclusion=str(raw.get("conclusion", "")),
            cta_to_ghosttowntest_com=str(raw.get("cta_to_ghosttowntest_com", "")),
            suggested_description=str(raw.get("suggested_description", "")),
            suggested_chapters_timestamps=tuple(raw.get("suggested_chapters_timestamps", [])),
            source_short_job_ids=tuple(job.job_id for job in short_jobs),
        )

    def _persist_artifacts(
        self,
        pack: CreativeAnglePack,
        short_jobs: tuple[AngleShortJob, ...],
        longform: LongFormAssemblyPlan,
    ) -> dict[str, str]:
        pack_dir = self.pack_dir(pack.angle_pack_id)
        paths: dict[str, Path] = {
            "creative_angle_pack": pack_dir / "creative_angle_pack.json",
            "longform_plan": pack_dir / "longform" / "LONGFORM_ASSEMBLY_PLAN.json",
            "longform_script": pack_dir / "longform" / "longform_script.md",
            "analytics_mapping_placeholders": pack_dir / "analytics_mapping_placeholders.json",
        }
        _atomic_json(paths["creative_angle_pack"], pack.to_dict())
        _atomic_json(paths["longform_plan"], longform.to_dict())
        _atomic_text(paths["longform_script"], self._longform_markdown(longform))
        _atomic_json(paths["analytics_mapping_placeholders"], {
            "schema_version": "creative_analytics_mapping.v1",
            "angle_pack_id": pack.angle_pack_id,
            "shorts": [self._analytics_placeholder(job) for job in short_jobs],
            "longform": {
                "longform_id": longform.longform_id,
                "youtube_video_id": None,
                "upload_attempt_id": None,
                "verification_receipt": None,
                "analytics_receipt": None,
                "country_analytics_receipt": None,
                "performance_score": None,
                "data_quality": "pending",
            },
            "analytics_network_called": False,
            "analytics_collected": False,
        })
        for job in short_jobs:
            directory = pack_dir / "shorts" / job.angle_id
            job_paths = {
                f"short_{job.angle_id}": directory / "angle_short_job.json",
                f"script_{job.angle_id}": directory / "script.md",
                f"caption_{job.angle_id}": directory / "caption.txt",
                f"thumbnail_{job.angle_id}": directory / "thumbnail_text.txt",
            }
            _atomic_json(job_paths[f"short_{job.angle_id}"], job.to_dict())
            _atomic_text(job_paths[f"script_{job.angle_id}"], job.script)
            _atomic_text(job_paths[f"caption_{job.angle_id}"], job.caption)
            _atomic_text(job_paths[f"thumbnail_{job.angle_id}"], job.thumbnail_text)
            paths.update(job_paths)
        return {key: self._relative(path) for key, path in paths.items()}

    def _write_receipt(
        self,
        *,
        timestamp: str,
        angle_pack_id: str,
        prompt_prefix_hash: str,
        input_hash: str,
        output_hash: str,
        gates: tuple[dict[str, Any], ...],
        source_receipt_references: dict[str, str],
        status: str,
        five_angles_generated: bool,
        short_jobs_created: int,
        longform_plan_created: bool,
        artifacts: dict[str, str],
    ) -> CreativeAnglePackReceipt:
        receipt = CreativeAnglePackReceipt(
            receipt_version=RECEIPT_VERSION,
            timestamp=timestamp,
            angle_pack_id=angle_pack_id,
            provider_type=self.provider.provider_type,
            model_id=self.provider.model_id,
            prompt_prefix_hash=prompt_prefix_hash,
            input_hash=input_hash,
            output_hash=output_hash,
            tokens_used=self.provider.tokens_used,
            cost_estimate=self.provider.cost_estimate,
            five_angles_generated=five_angles_generated,
            short_jobs_created=short_jobs_created,
            longform_plan_created=longform_plan_created,
            gates=gates,
            source_receipt_references=source_receipt_references,
            secrets_recorded=False,
            network_called=self.provider.network_called,
            publish_attempted=False,
            status=status,
            artifacts=artifacts,
            safety={
                "dry_run_unchanged": True,
                "full_autopilot_enabled": False,
                "supervised_autopilot_enabled": False,
                "live_publishing_enabled": False,
                "credentials_recorded": False,
                "raw_provider_response_recorded": False,
                "youtube_metadata_is_draft": True,
            },
        )
        path = self.receipt_path(angle_pack_id)
        _atomic_json(path, receipt.to_dict())
        CreativeAnglePackReceipt.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return receipt

    def _find_source(
        self, idea_id: str, batch_id: str | None,
    ) -> tuple[str, BusinessIdeaCandidate, VerdictRecord]:
        if batch_id:
            batch_ids = [batch_id]
        elif self.store.batches_root.is_dir():
            batch_ids = [path.name for path in sorted(self.store.batches_root.iterdir(), reverse=True) if path.is_dir()]
        else:
            batch_ids = []
        for candidate_batch in batch_ids:
            try:
                ideas = self.store.read(candidate_batch, "ideas")
                verdicts = self.store.read(candidate_batch, "verdicts")
            except AutopilotStoreError:
                if batch_id:
                    raise CreativeAnglePackError(f"batch is missing idea or LIT verdict artifacts: {candidate_batch}")
                continue
            idea_value = next((row for row in ideas if isinstance(row, dict) and row.get("idea_id") == idea_id), None)
            verdict_value = next((row for row in verdicts if isinstance(row, dict) and row.get("idea_id") == idea_id), None)
            if idea_value is not None and verdict_value is not None:
                return (
                    candidate_batch,
                    BusinessIdeaCandidate.from_dict(idea_value),
                    VerdictRecord.from_dict(verdict_value),
                )
        scope = f" in batch {batch_id}" if batch_id else ""
        raise CreativeAnglePackError(f"no stored idea and LIT verdict found for {idea_id}{scope}")

    def _source_references(self, batch_id: str) -> dict[str, str]:
        references = {
            "idea_artifact": self._relative(self.store.path(batch_id, "ideas")),
            "lit_verdict_artifact": self._relative(self.store.path(batch_id, "verdicts")),
        }
        if self.store.exists(batch_id, "receipt"):
            references["autopilot_receipt"] = self._relative(self.store.path(batch_id, "receipt"))
        return references

    def pack_dir(self, angle_pack_id: str) -> Path:
        self._validate_id(angle_pack_id, "angle_pack_id")
        return self.output_root / "creative_angle_packs" / angle_pack_id

    def receipt_path(self, angle_pack_id: str) -> Path:
        return self.pack_dir(angle_pack_id) / "ANGLE_PACK_RECEIPT.json"

    def longform_path(self, angle_pack_id: str) -> Path:
        return self.pack_dir(angle_pack_id) / "longform" / "LONGFORM_ASSEMBLY_PLAN.json"

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.output_root).as_posix()
        except ValueError as exc:
            raise CreativeAnglePackError("artifact path escapes output root") from exc

    @staticmethod
    def _safe_external_reference(path: Path) -> str:
        resolved = path.expanduser().resolve()
        try:
            return resolved.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved.name

    @staticmethod
    def _analytics_placeholder(job: AngleShortJob) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "angle_id": job.angle_id,
            "youtube_video_id": job.youtube_video_id,
            "upload_attempt_id": job.upload_attempt_id,
            "verification_receipt": job.verification_receipt,
            "analytics_receipt": job.analytics_receipt,
            "country_analytics_receipt": job.country_analytics_receipt,
            "performance_score": job.performance_score,
            "data_quality": job.data_quality,
        }

    @staticmethod
    def _longform_markdown(plan: LongFormAssemblyPlan) -> str:
        sections = [f"# {plan.longform_title}", plan.intro_script]
        for index, chapter in enumerate(plan.ordered_chapters):
            sections.extend([f"## {chapter['chapter_title']}", str(chapter["chapter_script"])])
            if index < len(plan.transition_lines):
                sections.append(plan.transition_lines[index])
        sections.extend(["## Conclusion", plan.conclusion, plan.cta_to_ghosttowntest_com])
        return "\n\n".join(sections)

    @staticmethod
    def _validate_id(value: str, name: str) -> None:
        if not value or not SAFE_ID.fullmatch(value) or Path(value).name != value:
            raise CreativeAnglePackError(f"invalid {name}")

    @staticmethod
    def _validate_verdict(verdict: dict[str, Any]) -> None:
        if not isinstance(verdict, dict):
            raise CreativeAnglePackError("stored LIT verdict is invalid")
        required = ("verdict_headline", "lit_score", "risk_level", "top_reason", "next_step")
        missing = [name for name in required if verdict.get(name) in (None, "")]
        if missing:
            raise CreativeAnglePackError("stored LIT verdict is incomplete: " + ", ".join(missing))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Phase 5B.5 creative angle packs and long-form plans.")
    parser.add_argument("--output-root", default="output", help="Generated output root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="Generate from a stored idea or LIT verdict fixture")
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument("--idea-id")
    source.add_argument("--lit-verdict-file")
    generate.add_argument("--batch-id", help="Optional source autopilot batch ID")
    generate.add_argument("--provider", choices=("deterministic", "fixture", "online_llm"), default="deterministic")
    generate.add_argument("--model", help="Required online model ID unless configured locally")
    generate.add_argument("--online-config", default=".local/creative_llm/config.json")
    generate.add_argument("--output-root", dest="output_root", default=argparse.SUPPRESS)
    return parser


def _provider_from_args(args: argparse.Namespace) -> CreativeGenerationProvider:
    if args.provider == "deterministic":
        return DeterministicCreativeGenerationProvider()
    if args.provider == "fixture":
        if not args.lit_verdict_file:
            raise CreativeProviderError("fixture provider requires --lit-verdict-file")
        _, _, fixture = load_lit_verdict_fixture(args.lit_verdict_file)
        return FixtureCreativeGenerationProvider(fixture.get("creative_output"))
    config = OnlineLLMConfig.load(model_override=args.model, config_path=args.online_config)
    return OnlineLLMCreativeGenerationProvider(config)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        provider = _provider_from_args(args)
        generator = CreativeAnglePackGenerator(
            provider=provider,
            output_root=args.output_root,
            online_provider_explicit=args.provider == "online_llm",
        )
        receipt = generator.generate(
            idea_id=args.idea_id,
            batch_id=args.batch_id,
            lit_verdict_file=args.lit_verdict_file,
        )
        print(f"Creative angle pack: {receipt.angle_pack_id}")
        print(f"Status: {receipt.status}")
        print(f"Short jobs: {receipt.short_jobs_created}")
        print(f"Receipt: {generator.receipt_path(receipt.angle_pack_id)}")
        if receipt.longform_plan_created:
            print(f"Long-form plan: {generator.longform_path(receipt.angle_pack_id)}")
        print("Full autopilot enabled: false")
        print("Supervised autopilot enabled: false")
        print("Live publishing enabled: false")
        return 0 if receipt.status == "completed" else 1
    except (
        CreativeAnglePackError,
        CreativeAngleContractError,
        CreativeGateError,
        CreativeProviderError,
        AutopilotStoreError,
        ValueError,
        OSError,
    ) as exc:
        print(f"Creative angle pack refused: {exc}", file=sys.stderr)
        return 1
