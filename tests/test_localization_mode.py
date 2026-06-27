from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_factory.agents.localization_agent import LocalizationAgent
from content_factory.config import Config
from content_factory.locales.catalog import labels_for
from content_factory.schemas import Idea, LitVerdict
from orchestrator import ContentFactoryOrchestrator


def _fast_orchestrator(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> ContentFactoryOrchestrator:
    orchestrator = ContentFactoryOrchestrator(config)

    def create_short(_script, _verdict, job_dir: Path, **_kwargs) -> Path:
        path = job_dir / "short.mp4"
        path.write_bytes(b"test-mp4")
        return path

    monkeypatch.setattr(orchestrator.video, "create_short", create_short)
    return orchestrator


def test_es_pr_localizes_script_captions_receipt_and_render_labels(
    tmp_path, monkeypatch
):
    config = Config(mode="mock", output_dir=tmp_path / "output")
    receipt_path = _fast_orchestrator(config, monkeypatch).run_batch(
        batch=1, locale="es-PR"
    )[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    script = Path(receipt["outputs"]["script_txt"]).read_text(encoding="utf-8")
    captions = Path(receipt["outputs"]["captions_srt"]).read_text(encoding="utf-8")

    for phrase in ("Probé esta idea", "Puntuación", "Riesgo principal", "Veredicto"):
        assert phrase in script
        assert phrase in captions
    assert "Prueba tu idea antes de construir" in script
    assert ".." not in script
    assert receipt["idea"]["name"] == "Agencia de creadores UGC con IA"
    assert receipt["localization"] == {
        "status": "success",
        "requested_locale": "es-PR",
        "resolved_locale": "es-PR",
        "fallback_locale": None,
        "localized_outputs": [
            "script.txt",
            "captions.srt",
            "thumbnail.jpg",
            "short.mp4",
        ],
        "warnings": [],
    }
    labels = labels_for("es-PR")
    assert labels["score"] == "PUNTUACIÓN"
    assert labels["cta_title"] == "PRUEBA PRIMERO"
    assert Path(receipt["outputs"]["thumbnail_jpg"]).stat().st_size > 0


def test_unsupported_locale_falls_back_to_english_with_receipt_warning(
    tmp_path, monkeypatch
):
    config = Config(mode="mock", output_dir=tmp_path / "output")
    receipt_path = _fast_orchestrator(config, monkeypatch).run_batch(
        batch=1, locale="fr-FR"
    )[0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    script = Path(receipt["outputs"]["script_txt"]).read_text(encoding="utf-8")

    assert script.startswith("I ran this business idea")
    assert receipt["localization"]["status"] == "fallback"
    assert receipt["localization"]["requested_locale"] == "fr-FR"
    assert receipt["localization"]["resolved_locale"] == "en-US"
    assert receipt["localization"]["fallback_locale"] == "en-US"
    assert receipt["localization"]["warnings"] == [
        "Unsupported locale fr-FR; fell back to en-US"
    ]
    assert receipt["warnings"] == [
        "Unsupported locale fr-FR; fell back to en-US"
    ]


def test_missing_spanish_phrase_falls_back_field_by_field_with_warning():
    verdict = LitVerdict(
        idea=Idea(name="Unknown idea", description="Unknown description", target_user="Unknown user"),
        verdict_headline="Unknown headline",
        lit_score=50,
        risk_level="unknown",
        top_reason="Unknown reason",
        next_step="Unknown next step",
    )
    agent = LocalizationAgent()
    resolution = agent.resolve("es-PR")
    localized, warnings = agent.localize_verdict(verdict, resolution)

    assert localized == verdict
    assert len(warnings) == 7
    assert all("used English" in warning for warning in warnings)


@pytest.mark.parametrize("alias", ["es", "es-US", "es-ES"])
def test_spanish_aliases_resolve_to_es_pr(alias):
    resolution = LocalizationAgent().resolve(alias)
    assert resolution.status == "success"
    assert resolution.resolved_locale == "es-PR"
