from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

import requests

from content_factory.schemas import Idea


class LitClient:
    """Small HTTP adapter for the LIT verdict endpoint."""

    def __init__(self, url: str, timeout_seconds: float = 20, api_key: str = ""):
        self.url = url.strip()
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key.strip()

    def test_idea(self, idea: Idea, locale: str = "en-US") -> Dict[str, Any]:
        if not self.url:
            raise ValueError("LIT_API_URL is blank")

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            self.url,
            json={
                "idea": asdict(idea),
                "answers": {f"q{i}": 4 for i in range(15)},
                "source": "shorts_factory",
                "locale": locale,
            },
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("LIT API response must be a JSON object")
        return payload
