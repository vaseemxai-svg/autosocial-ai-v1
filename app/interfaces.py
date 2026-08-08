"""
Every module talks to the next one ONLY through these interfaces.
This is what lets any single module (e.g. swap Reddit for Twitter as a trend
source, or swap the caption templates for a real LLM call) be replaced without
touching anything else.

Do not import a concrete module (e.g. RedditTrendCollector) directly from
another module's implementation — import the interface, and wire the concrete
class together in app/main.py (composition root) only.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Topic:
    """A candidate meme topic, regardless of where it came from."""
    text: str
    category: str  # e.g. "bollywood", "relatable", "indian"
    source: str  # e.g. "reddit", "mock", "twitter"
    score: float = 0.0


@dataclass
class GeneratedContent:
    """One fully generated, ready-to-review post."""
    topic: Topic
    image_path: str  # local filesystem path — always generated locally first
    caption: str
    hashtags: list[str]
    generated_at: str  # ISO timestamp
    drive_file_ids: dict = field(default_factory=dict)  # filled in after upload


@dataclass
class PublishResult:
    success: bool
    instagram_post_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PostInsights:
    instagram_post_id: str
    likes: int
    comments: int
    reach: int
    fetched_at: str


class TrendCollectorInterface(ABC):
    @abstractmethod
    def get_topics(self, limit: int = 5) -> list[Topic]:
        """Return candidate topics, best first."""


class ContentGeneratorInterface(ABC):
    @abstractmethod
    def generate(self, topic: Topic) -> GeneratedContent:
        """Turn one topic into an image + caption + hashtags, saved locally."""


class StorageInterface(ABC):
    @abstractmethod
    def validate(self, content: GeneratedContent) -> bool:
        """Local validation (file exists, non-zero size, caption non-empty, etc)."""

    @abstractmethod
    def upload(self, content: GeneratedContent) -> GeneratedContent:
        """Upload validated local content to Drive. Returns content with drive_file_ids set.
        Must be safe to call even if Drive is temporarily unreachable — raise, don't crash
        the caller's ability to keep the content available locally for retry."""


class PublisherInterface(ABC):
    @abstractmethod
    def publish_now(self, content: GeneratedContent) -> PublishResult:
        """Publish ONE piece of content immediately. Only ever called from a human
        action (the web UI's Post Now button). Never called by the scheduler."""


class AnalyticsInterface(ABC):
    @abstractmethod
    def fetch_insights(self, instagram_post_id: str) -> PostInsights:
        """Pull performance data for a post that was actually published."""


class SchedulerInterface(ABC):
    @abstractmethod
    def start(self) -> None:
        """Start the twice-daily generation job. Generation only — never publishes."""
