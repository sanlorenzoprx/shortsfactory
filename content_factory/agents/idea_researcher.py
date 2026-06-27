from __future__ import annotations

from typing import List

from content_factory.schemas import Idea


class IdeaResearcher:
    """Mock idea source for MVP.

    Production research comes later. For now the pipeline must be deterministic,
    cheap, and testable.
    """

    SEED_IDEAS = [
        Idea(
            name="AI UGC Creator Agency",
            description="A service that creates short-form product videos for brands using AI avatars and scripts.",
            target_user="small ecommerce brands",
            market="US",
        ),
        Idea(
            name="Niche Meal Prep for Busy Nurses",
            description="Healthy, shift-friendly meal prep subscriptions for nurses working 12-hour shifts.",
            target_user="busy healthcare workers",
            market="US",
        ),
        Idea(
            name="Micro-SaaS for TikTok Creators",
            description="A lightweight analytics and content calendar tool for small TikTok creators.",
            target_user="solo creators",
            market="US",
        ),
    ]

    def get_trending_ideas(self, count: int = 1) -> List[Idea]:
        if count < 1:
            raise ValueError("count must be >= 1")
        return self.SEED_IDEAS[:count]
