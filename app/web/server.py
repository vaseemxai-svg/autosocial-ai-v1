import logging

from flask import Flask, jsonify, redirect, render_template, send_file, url_for

from app.config import config
from app.publisher.publisher import GraphAPIPublisher
from app.scheduler.scheduler import GenerationScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
scheduler = GenerationScheduler()
publisher = GraphAPIPublisher()


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
