"""
Thin wrapper around the official Instagram Graph API. This file intentionally
contains NO browser automation, NO login/password handling, and NO session
cookies — only HTTPS calls to graph.facebook.com using a long-lived access
token the human generated themselves in the Meta developer console.
"""
import logging
import time

import requests

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

logger = logging.getLogger(__name__)

# --- Blocker 1: container readiness polling ---------------------------------
_CONTAINER_STATUS_ENDPOINT = "{base}/{account_id}"  # GET ?fields=status_code
_CONTAINER_POLL_INTERVAL_SECONDS = 3
_CONTAINER_HARD_TIMEOUT_SECONDS = 30
_CONTAINER_TERMINAL_STATES = {"FINISHED", "ERROR", "EXPIRED"}


class InstagramGraphAPIError(Exception):
    pass


class InstagramGraphAPIClient:
    def __init__(self, ig_account_id: str, access_token: str):
        self.ig_account_id = ig_account_id
        self.access_token = access_token

    def publish_image(self, image_url: str, caption: str) -> str:
        """Two-step Graph API publish flow. Requires image_url to be a public
        HTTPS URL (Graph API cannot accept a local file directly) — in V1 this
        is the Google Drive share link produced by the storage module.
        Returns the published media id.
        """
        container_id = self._create_media_container(image_url, caption)
        # Blocker 1: never call /media_publish before the container is ready.
        self._wait_for_container_ready(container_id)
        return self._publish_container(container_id)

    def _wait_for_container_ready(self, container_id: str) -> None:
        """Poll the container's status_code until FINISHED or a hard timeout.

        Raises InstagramGraphAPIError if the container reaches ERROR or
        EXPIRED, or if the 30-second hard timeout elapses. Never proceeds
        to /media_publish in those cases.
        """
        deadline = time.time() + _CONTAINER_HARD_TIMEOUT_SECONDS
        while True:
            if time.time() > deadline:
                raise InstagramGraphAPIError(
                    f"Media container {container_id} did not reach FINISHED "
                    f"within {_CONTAINER_HARD_TIMEOUT_SECONDS}s — aborting "
                    "publish. Check the container status on the Meta API."
                )
            status = self._get_container_status(container_id)
            if status == "FINISHED":
                logger.info("Container %s status=FINISHED — proceeding to publish", container_id)
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramGraphAPIError(
                    f"Media container {container_id} reached status={status} — "
                    "publish blocked. Create a new container and retry."
                )
            logger.info("Container %s status=%s — polling again in %ss", container_id, status, _CONTAINER_POLL_INTERVAL_SECONDS)
            time.sleep(_CONTAINER_POLL_INTERVAL_SECONDS)

    def _get_container_status(self, container_id: str) -> str:
        """Read-only status check: GET /{container_id}?fields=status_code."""
        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": self.access_token},
            timeout=15,
        )
        data = resp.json()
        status = data.get("status_code", "")
        if not status:
            # Treat an unreadable status as a terminal failure (do not poll forever)
            raise InstagramGraphAPIError(
                f"Container {container_id} status unreadable: {data} — publish blocked."
            )
        return status

    def _create_media_container(self, image_url: str, caption: str) -> str:
        resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_account_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        data = resp.json()
        if "id" not in data:
            raise InstagramGraphAPIError(f"Failed to create media container: {data}")
        return data["id"]

    def _publish_container(self, container_id: str) -> str:
        resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_account_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
            timeout=30,
        )
        data = resp.json()
        if "id" not in data:
            raise InstagramGraphAPIError(f"Failed to publish container: {data}")
        return data["id"]

    def verify_credentials(self) -> dict:
        """Verify the access token + account ID WITHOUT publishing anything.

        Calls GET /{ig-user-id}?fields=id,username,media_count on the official
        Graph API. A 200 response means the credentials are valid and the
        account is reachable; no media container or post is created. Used by
        the pre-publish check so a misconfigured .env fails loudly before any
        container is created (containers expire in 24h if never published).
        """
        resp = requests.get(
            f"{GRAPH_API_BASE}/{self.ig_account_id}",
            params={"fields": "id,username,media_count", "access_token": self.access_token},
            timeout=30,
        )
        data = resp.json()
        if "id" not in data:
            raise InstagramGraphAPIError(f"Credential verification failed: {data}")
        return data

    @property
    def container_poll_interval(self) -> int:
        """Expose the polling interval for tests (default 3s, tests may override)."""
        global _CONTAINER_POLL_INTERVAL_SECONDS
        return _CONTAINER_POLL_INTERVAL_SECONDS

    @container_poll_interval.setter
    def container_poll_interval(self, value: int) -> None:
        global _CONTAINER_POLL_INTERVAL_SECONDS
        _CONTAINER_POLL_INTERVAL_SECONDS = value

    @property
    def container_hard_timeout(self) -> int:
        """Expose the hard timeout for tests (default 30s)."""
        return _CONTAINER_HARD_TIMEOUT_SECONDS

    def get_insights(self, media_id: str) -> dict:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{media_id}/insights",
            params={"metric": "impressions,reach,likes,comments", "access_token": self.access_token},
            timeout=30,
        )
        return resp.json()
