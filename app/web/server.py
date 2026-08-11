import logging

import os

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

from app.config import config
from app.publisher.publisher import GraphAPIPublisher
from app.scheduler.scheduler import GenerationScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
scheduler = GenerationScheduler()
publisher = GraphAPIPublisher()


# ---------------------------------------------------------------------------
# Reusable auth gate — ONE helper, ONE source of truth (config.web_api_secret)
# ---------------------------------------------------------------------------
def check_authorization():
    """Shared-secret auth check used by BOTH /post-now and /generate.

    - Reads the secret from `config.web_api_secret` (the single centralized
      place that reads the WEB_API_SECRET env var). NEVER reads os.environ
      directly.
    - No secret configured -> localhost-only behaviour (unchanged from v1.0.4).
    - Secret configured -> caller MUST send `Authorization: Bearer <secret>`.
    - Returns the JSON 401 response if unauthorized, None otherwise.
    """
    secret = config.web_api_secret
    if not secret:
        return None
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer ") or auth_header[7:] != secret:
        logger.warning("Unauthorized attempt — missing or wrong WEB_API_SECRET")
        return jsonify({"success": False, "error": "Unauthorized: missing or invalid Authorization header"}), 401
    return None


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    # Generate one item on demand if the queue is empty, so the UI is never
    # blank when you open it (useful for manual testing / mock mode demo).
    if not scheduler.queue:
        scheduler.run_once()
    latest = scheduler.queue[-1] if scheduler.queue else None
    return render_template("preview.html", content=latest, mock_mode=config.mock_mode, queue_len=len(scheduler.queue))


@app.route("/image/<path:filename>")
def serve_image(filename):
    return send_file(config.local_memes_dir / filename)


@app.route("/generate", methods=["POST"])
def generate():
    """On-demand content generation — same auth gate as /post-now, because an
    unauthenticated caller could otherwise flood generation (and any future
    Drive uploads). Protected via the same `check_authorization()` helper —
    ONE helper, ONE source of truth."""
    unauthorized = check_authorization()
    if unauthorized is not None:
        return unauthorized
    scheduler.run_once()
    return redirect(url_for("index"))


@app.route("/verify-credentials", methods=["POST"])
def verify_credentials():
    """Day-1 pre-publish check: verifies IG credentials via the official
    Graph API WITHOUT creating any media container or post."""
    if config.mock_mode:
        return jsonify({"success": True, "mode": "mock",
                        "message": "Mock mode — no real credentials configured yet"})
    try:
        config.require_live_credentials()
        from app.publisher.graph_api import InstagramGraphAPIClient, InstagramGraphAPIError
        client = InstagramGraphAPIClient(
            ig_account_id=config.active_account.ig_account_id,
            access_token=config.active_account.ig_access_token,
        )
        account = client.verify_credentials()
        return jsonify({"success": True, "account": account})
    except InstagramGraphAPIError as exc:
        return jsonify({"success": False, "error": str(exc)}), 401


@app.route("/post-now", methods=["POST"])
def post_now():
    """The ONLY route in this app that results in a real Instagram post.

    Protected by the shared WEB_API_SECRET via `check_authorization()`.
    No secret configured -> localhost-only behavior preserved.
    """
    unauthorized = check_authorization()
    if unauthorized is not None:
        return unauthorized
    if not scheduler.queue:
        return jsonify({"success": False, "error": "Nothing queued to post"}), 400
    content = scheduler.queue[-1]
    result = publisher.publish_now(content)
    return jsonify(
        {"success": result.success, "instagram_post_id": result.instagram_post_id, "error": result.error}
    )


def main():
    scheduler.start()
    app.run(host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    main()
