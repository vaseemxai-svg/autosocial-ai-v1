import logging
from datetime import datetime, timezone

from app.config import config
from app.interfaces import GeneratedContent, PublisherInterface, PublishResult
from app.publisher.graph_api import InstagramGraphAPIClient, InstagramGraphAPIError

logger = logging.getLogger(__name__)


class GraphAPIPublisher(PublisherInterface):
    """publish_now() is the single method that can make a real post happen.
    It is called from exactly one place in this codebase: the /post-now route
    in app/web/server.py, which only runs when a human clicks the button.
    The scheduler (app/scheduler) never imports or calls this class."""

    def publish_now(self, content: GeneratedContent) -> PublishResult:
        if config.mock_mode:
            return self._mock_publish(content)
        return self._live_publish(content)

    def _mock_publish(self, content: GeneratedContent) -> PublishResult:
        logger.info("[MOCK] Would publish to Instagram: %s", content.topic.text)
        fake_id = f"mock_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        return PublishResult(success=True, instagram_post_id=fake_id)

    def _live_publish(self, content: GeneratedContent) -> PublishResult:
        config.require_live_credentials()
        image_url = content.drive_file_ids.get("public_url")
        if not image_url:
            return PublishResult(
                success=False,
                error="No public image URL available — content must be uploaded to "
                "Drive (with a shareable link) before it can be published.",
            )
        client = InstagramGraphAPIClient(
            ig_account_id=config.active_account.ig_account_id,
            access_token=config.active_account.ig_access_token,
        )
        full_caption = content.caption + "\n\n" + " ".join(content.hashtags)
        try:
            post_id = client.publish_image(image_url, full_caption)
            return PublishResult(success=True, instagram_post_id=post_id)
        except InstagramGraphAPIError as e:
            logger.error("Publish failed: %s", e)
            return PublishResult(success=False, error=str(e))
