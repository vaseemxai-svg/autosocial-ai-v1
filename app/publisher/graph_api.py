"""
Thin wrapper around the official Instagram Graph API. This file intentionally
contains NO browser automation, NO login/password handling, and NO session
cookies — only HTTPS calls to graph.facebook.com using a long-lived access
token the human generated themselves in the Meta developer console.
"""
import requests

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


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
        return self._publish_container(container_id)

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

    def get_insights(self, media_id: str) -> dict:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{media_id}/insights",
            params={"metric": "impressions,reach,likes,comments", "access_token": self.access_token},
            timeout=30,
        )
        return resp.json()
