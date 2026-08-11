"""Blocker 5 — local rolling 24-hour publish counter.

A safety limit of 15 posts per rolling 24 hours, enforced LOCALLY before any
Meta API call. If the limit is reached, publishing is refused with a logged
reason and no Meta endpoint is touched.

Persisted to a JSON file (output/logs/publish_log.json) so the window survives
restarts and is shared across processes. In-process guard prevents races.

This is NOT Meta's official rate limit (50 posts/24h) — it is a stricter
application-level safety budget to prevent accidental spam from a misconfigured
scheduler.
"""
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_SAFETY_LIMIT = 15
WINDOW_SECONDS = 24 * 60 * 60

_lock = threading.Lock()


class PublishRateLimiter:
    def __init__(self, log_path: Path):
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[float]:
        if self._log_path.exists():
            try:
                with open(self._log_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Publish log unreadable — starting fresh counter")
        return []

    def _save(self, timestamps: list[float]) -> None:
        with open(self._log_path, "w") as f:
            json.dump(timestamps, f)

    def _recent(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - WINDOW_SECONDS
        return [t for t in timestamps if t > cutoff]

    def can_publish(self, now: float | None = None) -> tuple[bool, str]:
        """Thread-safe check. Returns (allowed, reason).

        Reason is a human-readable string; empty when allowed.
        """
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        with _lock:
            timestamps = self._recent(self._load(), now)
            if len(timestamps) >= LOCAL_SAFETY_LIMIT:
                oldest = min(timestamps)
                reason = (
                    f"Local rolling 24h safety limit reached ({LOCAL_SAFETY_LIMIT} posts/"
                    f"{WINDOW_SECONDS // 3600}h). Oldest publish in window: "
                    f"{datetime.fromtimestamp(oldest, tz=timezone.utc):%Y-%m-%d %H:%M UTC}. "
                    "Publish refused — no Meta endpoint was called."
                )
                logger.error(reason)
                return False, reason
            return True, ""

    def record_publish(self, now: float | None = None) -> None:
        """Record a successfully-published post (call AFTER the API succeeds)."""
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        with _lock:
            timestamps = self._load()
            timestamps.append(now)
            self._save(self._recent(timestamps, now))
        logger.info("Rolling counter: %d publish(es) in the last 24h", len(self._recent(self._load(), now)))
