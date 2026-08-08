"""
Trend Collector — V1 implementation
=====================================
V1 uses the bundled mock topic list (mock_data/sample_trends.json) so the
pipeline is testable offline. The collector only implements
TrendCollectorInterface, so future V2 sources (Reddit, Twitter, RSS) can be
added as new classes and swapped in get_collector() without touching the
Scheduler, Generator, or any other module.

Ordering: topics are returned best-first by `score` (descending), matching
the interface contract.
"""
import json
import logging
import os
import random
from pathlib import Path
from typing import Optional

from app.config import config
from app.interfaces import Topic, TrendCollectorInterface

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MOCK_TRENDS_PATH = BASE_DIR / "mock_data" / "sample_trends.json"


class MockTrendCollector(TrendCollectorInterface):
    """V1 source: curated Hinglish topic list bundled in the repo."""

    def __init__(self, trends_path: Optional[str] = None):
        self.trends_path = Path(trends_path) if trends_path else MOCK_TRENDS_PATH

    def get_topics(self, limit: int = 5) -> list[Topic]:
        if not self.trends_path.exists():
            logger.warning("Trends file missing at %s — returning empty list", self.trends_path)
            return []
        try:
            raw = json.loads(self.trends_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load trends: %s", exc)
            return []
        topics = [
            Topic(
                text=item.get("text", ""),
                category=item.get("category", "relatable"),
                source="mock",
                score=float(item.get("score", 0.0)),
            )
            for item in raw
            if item.get("text", "").strip()
        ]
        topics.sort(key=lambda t: t.score, reverse=True)
        return topics[:limit]


class RandomTrendCollector(TrendCollectorInterface):
    """Slight variation of MockTrendCollector that randomises ordering with a
    bias towards high-score topics — prevents the same topic from being picked
    at both generation slots on the same day. V1 convenience wrapper; same
    interface, same mock source."""

    def __init__(self, trends_path: Optional[str] = None):
        self._inner = MockTrendCollector(trends_path)

    def get_topics(self, limit: int = 5) -> list[Topic]:
        topics = self._inner.get_topics(limit=limit)
        # Weighted random: higher score => more likely to be picked first.
        weights = [max(t.score, 0.1) for t in topics]
        if topics and sum(weights) > 0:
            chosen = random.choices(topics, weights=weights, k=min(limit, len(topics)))
            chosen.sort(key=lambda t: t.score, reverse=True)
            return chosen
        return topics


def get_collector(mode: Optional[str] = None) -> TrendCollectorInterface:
    """Return the configured collector. Mode comes from .env so behaviour can
    be toggled without touching code.

    - MOCK_DEFAULT: plain best-first ordering (deterministic, good for tests)
    - RANDOMISED: weighted random ordering (better for daily variety)
    - Anything else (or unset): MOCK_DEFAULT
    """
    mode = (mode or os.getenv("TREND_COLLECTOR_MODE", "MOCK_DEFAULT")).upper()
    if mode == "RANDOMISED":
        return RandomTrendCollector()
    return MockTrendCollector()
