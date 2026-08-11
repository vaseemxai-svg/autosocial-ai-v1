import logging
from datetime import datetime, timezone

from app.config import config
from app.interfaces import GeneratedContent, PublisherInterface, PublishResult
from app.publisher.graph_api import InstagramGraphAPIClient, InstagramGraphAPIError
from app.publisher.image_validator import validate_image_url
from app.publisher.rate_limiter import PublishRateLimiter

logger = logging.getLogger(__name__)

# Blocker 5: local rolling 24h safety counter (shared per-process)
_rate_limiter = PublishRateLimiter(config.local_logs_dir / "publish_log.json")


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
        # Blocker 2 — hard live-publish safety gate (default False).
        if not config.enable_live_instagram_publish:
            reason = (
                "Live Instagram publishing is DISABLED "
                "(ENABLE_LIVE_INSTAGRAM_PUBLISH=false). No Instagram media "
                "container will be created and /media_publish will NOT be "
                "called. Set ENABLE_LIVE_INSTAGRAM_PUBLISH=true to allow."
            )
            logger.error(reason)
            return PublishResult(success=False, error=reason)

        # Blocker 4a — credentials must exist before anything else.
        config.require_live_credentials()

        # Blocker 4b — read-only credential verification BEFORE creating any
        # container. Fails safely if the token/account are invalid; never logs
        # the token value.
        client = InstagramGraphAPIClient(
            ig_account_id=config.active_account.ig_account_id,
            access_token=config.active_account.ig_access_token,
        )
        try:
            client.verify_credentials()
        except InstagramGraphAPIError as e:
            logger.error("Credential verification failed — publish blocked: %s", e)
            return PublishResult(success=False, error=f"Credentials invalid: {e}")

        # Blocker 5 — local rolling 24h safety limit (15 posts).
        allowed, reason = _rate_limiter.can_publish()
        if not allowed:
            return PublishResult(success=False, error=reason)

        image_url = content.drive_file_ids.get("public_url")
        if not image_url:
            return PublishResult(
                success=False,
                error="No public image URL available — content must be uploaded to "
                "Drive (with a shareable link) before it can be published.",
            )

        # Blocker 3 — validate the image URL before it goes to Meta:
        # public reachability, HTTP success, JPEG/PNG only, < 8 MB.
        try:
            validate_image_url(image_url)
        except ValueError as e:
            logger.error("Image URL rejected — publish blocked: %s", e)
            return PublishResult(success=False, error=str(e))

        full_caption = content.caption + "\n\n" + " ".join(content.hashtags)
        try:
            post_id = client.publish_image(image_url, full_caption)
            _rate_limiter.record_publish()  # count only actual publishes
            return PublishResult(success=True, instagram_post_id=post_id)
        except InstagramGraphAPIError as e:
            logger.error("Publish failed: %s", e)
            return PublishResult(success=False, error=str(e))
