"""Blocker 3 — image URL validation before sending to Meta.

Checks, WITHOUT downloading or re-uploading the image:
1. URL is publicly reachable (GET with stream=True — bytes never buffered)
2. HTTP success response (2xx)
3. Content-Type is image/jpeg or image/png
4. Content-Length < 8 MB

Raises ValueError with a clear reason on any failure.
"""
import logging

import requests

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png"}

logger = logging.getLogger(__name__)


def validate_image_url(image_url: str) -> None:
    """Validate that image_url is a public, JPEG/PNG image under 8 MB.

    Uses a streamed HEAD+GET: no image bytes are buffered or re-uploaded.
    Raises ValueError if the URL is not usable for Meta publishing.
    """
    if not image_url or not image_url.strip().startswith("https://"):
        raise ValueError(
            f"Image URL is not a public HTTPS URL: {image_url!r}. "
            "Meta's Graph API only accepts publicly reachable URLs."
        )

    # Check 1-2: publicly reachable + HTTP success (HEAD first; fall back to GET)
    headers = {"User-Agent": "AutoSocialAI/1.0"}
    try:
        head = requests.head(image_url, headers=headers, timeout=15, allow_redirects=True)
        if head.status_code // 100 != 2:
            get = requests.get(image_url, headers=headers, stream=True, timeout=15, allow_redirects=True)
            get.close()
            if get.status_code // 100 != 2:
                raise ValueError(
                    f"Image URL is not publicly reachable (HTTP {get.status_code} "
                    f"after redirects): {image_url}"
                )
            resp = get
        else:
            resp = head
    except requests.RequestException as e:
        raise ValueError(
            f"Image URL could not be reached at all ({type(e).__name__}): {image_url}"
        ) from e

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    content_length = resp.headers.get("Content-Length")

    if content_type not in ALLOWED_TYPES:
        raise ValueError(
            f"Image Content-Type '{content_type}' is not allowed — Meta accepts "
            f"only JPEG/PNG ({image_url}). Supported: {', '.join(sorted(ALLOWED_TYPES))}."
        )

    if content_length is not None:
        try:
            size = int(content_length)
        except ValueError:
            size = None
        if size is not None and size >= MAX_BYTES:
            raise ValueError(
                f"Image is {size / (1024*1024):.1f} MB — exceeds the 8 MB limit "
                f"({image_url})."
            )
    else:
        logger.warning(
            "Image URL has no Content-Length header — size cannot be verified "
            "before upload (%s).", image_url
        )

    logger.info(
        "Image URL validated: type=%s, size=%s (%s)", content_type,
        content_length or "unknown", image_url[:120]
    )
