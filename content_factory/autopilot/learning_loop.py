from __future__ import annotations

from .autopilot_models import BusinessIdeaCandidate, LearningLoopRecommendation, TrendSignal


CREATED_AT = "2026-06-29T00:09:00+00:00"


class LearningLoop:
    def recommend(
        self,
        *,
        batch_id: str,
        performance: dict,
        trends: list[TrendSignal],
        ideas: list[BusinessIdeaCandidate],
        jobs: list[dict[str, str]],
        batch_size: int,
    ) -> LearningLoopRecommendation:
        top = performance.get("top_jobs", [])
        if not top:
            query = trends[0].topic if trends else "adjacent buyer pain workflows"
            return LearningLoopRecommendation(
                batch_id=batch_id, status="ready", recommendation_type="revise_angle",
                message="Revise the buyer/pain angle because no simulated publish passed every machine gate.",
                next_trend_queries=(f"{query} buyer pain", f"{query} paid pilot"),
                next_batch_size=max(1, batch_size), created_at=CREATED_AT,
            )
        best_job_id = str(top[0].get("job_id", ""))
        job = next((value for value in jobs if value.get("job_id") == best_job_id), jobs[0] if jobs else {})
        idea = next((value for value in ideas if value.idea_id == job.get("idea_id")), ideas[0])
        trend = next((value for value in trends if value.trend_id == idea.source_trend_id), trends[0])
        return LearningLoopRecommendation(
            batch_id=batch_id, status="ready", recommendation_type="repeat_winner",
            message=f"Repeat the {trend.topic} angle with a sharper {idea.angle} hook; this is a simulated local signal, not statistical proof.",
            next_trend_queries=(f"{trend.topic} payment proof", f"{trend.topic} urgent buyer workflow"),
            next_batch_size=max(1, batch_size), created_at=CREATED_AT,
        )
