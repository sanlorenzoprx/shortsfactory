from __future__ import annotations


LOCALE_ALIASES = {
    "en": "en-US",
    "en-us": "en-US",
    "es": "es-PR",
    "es-pr": "es-PR",
    "es-us": "es-PR",
    "es-es": "es-PR",
}


ENGLISH_LABELS = {
    "thumbnail_title": "GHOST TOWN\nTEST",
    "score": "SCORE",
    "thumbnail_question": "Would you build it?",
    "hook_title": "I TESTED THIS IDEA",
    "risk_level": "Risk level",
    "reason_title": "WHY IT MATTERS",
    "verdict_title": "VERDICT",
    "cta_title": "DO NOT BUILD BLIND",
    "footer_product": "LIT Ghost Town Test",
    "footer_cta": "Test the idea before you build.",
}


SPANISH_LABELS = {
    "thumbnail_title": "PRUEBA DE\nMERCADO",
    "score": "PUNTUACIÓN",
    "thumbnail_question": "¿Lo construirías?",
    "hook_title": "PROBÉ ESTA IDEA",
    "risk_level": "Nivel de riesgo",
    "reason_title": "POR QUÉ IMPORTA",
    "verdict_title": "VEREDICTO",
    "cta_title": "PRUEBA PRIMERO",
    "footer_product": "Prueba Ghost Town de LIT",
    "footer_cta": "Prueba la idea antes de construir.",
}


SPANISH_PHRASES = {
    "AI UGC Creator Agency": "Agencia de creadores UGC con IA",
    "A service that creates short-form product videos for brands using AI avatars and scripts.": (
        "Un servicio que crea videos cortos de productos para marcas con avatares y guiones de IA."
    ),
    "small ecommerce brands": "marcas pequeñas de comercio electrónico",
    "Niche Meal Prep for Busy Nurses": "Comidas preparadas para enfermeros con poco tiempo",
    "Healthy, shift-friendly meal prep subscriptions for nurses working 12-hour shifts.": (
        "Suscripciones de comidas saludables para enfermeros que trabajan turnos de 12 horas."
    ),
    "busy healthcare workers": "profesionales de salud con poco tiempo",
    "Micro-SaaS for TikTok Creators": "Micro-SaaS para creadores de TikTok",
    "A lightweight analytics and content calendar tool for small TikTok creators.": (
        "Una herramienta sencilla de analítica y calendario para pequeños creadores de TikTok."
    ),
    "solo creators": "creadores independientes",
    "Build a tiny test now": "Haz una prueba pequeña ahora",
    "Promising, but niche down": "Promete, pero enfócate en un nicho",
    "Ghost town risk": "Riesgo de mercado fantasma",
    "You have the advantage.": "Tienes la ventaja.",
    "Test the narrow offer": "Prueba la oferta específica",
    "medium": "medio",
    "medium-high": "medio-alto",
    "high": "alto",
    "low": "bajo",
    "The idea has a clear buyer, but the first offer must be narrow.": (
        "La idea tiene un comprador claro, pero la primera oferta debe ser específica."
    ),
    "The market is real, but the positioning is too broad.": (
        "El mercado existe, pero el posicionamiento es demasiado amplio."
    ),
    "The idea sounds attractive, but demand proof is weak.": (
        "La idea suena atractiva, pero falta evidencia de demanda."
    ),
    "Clear demand, strong LIT score, and unfair advantage. The conditions are right.": (
        "Hay demanda clara, una puntuación LIT sólida y una ventaja difícil de copiar. "
        "Las condiciones son favorables."
    ),
    "The buyer is clear but demand still needs proof.": (
        "El comprador está claro, pero la demanda todavía necesita evidencia."
    ),
    "Pre-sell one painful use case before building a full product.": (
        "Prevende un caso de uso urgente antes de crear el producto completo."
    ),
    "Pick one urgent buyer and one painful job-to-be-done.": (
        "Escoge un comprador urgente y un problema importante por resolver."
    ),
    "Run interviews and collect willingness-to-pay signals first.": (
        "Primero haz entrevistas y busca señales de intención de pago."
    ),
    "Build a minimal MVP and test with your first 3 customers.": (
        "Crea un MVP mínimo y pruébalo con tus primeros 3 clientes."
    ),
    "Pre-sell the smallest useful version.": "Prevende la versión útil más pequeña.",
}


def resolve_locale(locale: str) -> str | None:
    return LOCALE_ALIASES.get(locale.strip().lower())


def labels_for(locale: str) -> dict[str, str]:
    return SPANISH_LABELS if locale == "es-PR" else ENGLISH_LABELS


def translate_to_spanish(text: str) -> str | None:
    return SPANISH_PHRASES.get(text)
