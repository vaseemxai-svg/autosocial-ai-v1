import logging
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

from app.config import config
from app.publisher.publisher import GraphAPIPublisher
from app.scheduler.scheduler import GenerationScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
scheduler = GenerationScheduler()
publisher = GraphAPIPublisher()


def require_post_now_token(fn):
    """Guards any route that can cause a real side effect. In mock mode this
    is a no-op (nothing real can happen). Once MOCK_MODE=false, the caller
    must send X-Post-Now-Token matching POST_NOW_TOKEN from .env — this is
    what makes it safe to bind 0.0.0.0 for Docker without letting anyone on
    the same network trigger a real Instagram post."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if config.mock_mode:
            return fn(*args, **kwargs)
        sent = request.headers.get("X-Post-Now-Token", "")
        if not config.post_now_token or sent != config.post_now_token:
            logger.warning("Blocked unauthorized call to %s (bad/missing token)", request.path)
            return jsonify({"success": False, "error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


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
@require_post_now_token
def generate():
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
@require_post_now_token
def post_now():
    """The ONLY route in this app that results in a real Instagram post."""
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
