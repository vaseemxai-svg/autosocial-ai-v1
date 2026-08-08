import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import config
from app.content_generator.generator import TemplateContentGenerator
from app.interfaces import SchedulerInterface
from app.storage.drive_uploader import LocalFirstDriveStorage
from app.trend_collector.collector import get_collector

logger = logging.getLogger(__name__)


class GenerationScheduler(SchedulerInterface):
    """Runs at GENERATION_TIMES (default 9 AM / 7 PM). Produces content and
    queues it for human review in the web UI. This class has no reference to
    PublisherInterface at all — it CANNOT publish, by construction, not just
    by convention."""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=config.timezone)
        self.collector = get_collector()
        self.generator = TemplateContentGenerator()
        self.storage = LocalFirstDriveStorage()
        self.queue: list = []  # in-memory queue the web UI reads from

    def start(self) -> None:
        for t in config.generation_times:
            hour, minute = t.split(":")
            self.scheduler.add_job(self.run_once, "cron", hour=int(hour), minute=int(minute))
        self.scheduler.start()
        logger.info("Scheduler started for times: %s (%s)", config.generation_times, config.timezone)

    def run_once(self):
        topics = self.collector.get_topics(limit=1)
        if not topics:
            logger.warning("No topics available this run — skipping")
            return None
        content = self.generator.generate(topics[0])
        if not self.storage.validate(content):
            logger.error("Generated content failed validation — not queuing")
            return None
        try:
            content = self.storage.upload(content)
        except NotImplementedError:
            logger.info("Drive upload not configured yet — content stays queued locally")
        self.queue.append(content)
        logger.info("Queued new content for review: %s", content.topic.text)
        return content
