"""P2 Blockers suite — CTO audit fixes (Blockers 1-5).

Runs INSIDE Docker. Fully mock-only: all Instagram API calls are stubbed with
unittest.mock; no live credentials, no live posts, zero network to Meta.
Covers the 12 required scenarios:

 1. Container FINISHED -> publish allowed (mock mode + gate open)
 2. Container PROCESSING -> polling continues until FINISHED
 3. Container ERROR -> publish blocked
 4. Container EXPIRED -> publish blocked
 5. 30-second timeout -> publish blocked
 6. ENABLE_LIVE_INSTAGRAM_PUBLISH=false -> no live API call
 7. Invalid/private image URL -> blocked
 8. Wrong content type -> blocked
 9. Image > 8 MB -> blocked
10. Missing/invalid credentials -> blocked
11. Rate limit >= 15 -> blocked
12. Existing P0 behavior intact (import + publisher contract check)
"""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from unittest import mock

import requests

import os as _os
_app_root = "/app" if _os.path.isdir("/app") else _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _app_root)

from app.config import config
from app.publisher.graph_api import InstagramGraphAPIClient, InstagramGraphAPIError
from app.publisher.image_validator import validate_image_url
from app.publisher.publisher import GraphAPIPublisher
from app.publisher.rate_limiter import PublishRateLimiter

results = []
_call_log = []  # records every requests call during tests


def check(name):
    def deco(fn):
        def wrapper():
            _call_log.clear()
            try:
                fn()
                results.append((name, "PASS", ""))
            except AssertionError as e:
                results.append((name, "FAIL", str(e)))
            except Exception as e:
                import traceback as _tb
                results.append((name, "FAIL", f"{type(e).__name__}: {e}\n" + "".join(_tb.format_exception(e))[-600:]))
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# helpers: fake Graph API responses
# ---------------------------------------------------------------------------

def _make_container_status_response(status_code: str, delay: float = 0):
    """Factory for a mock response returning {"status_code": status}."""
    resp = mock.MagicMock()
    resp.json.return_value = {"status_code": status_code, "id": "mock_container"}
    return resp


def _mock_requests_with_status_sequence(statuses):
    """Patch requests so container polling sees the given status sequence.

    GET /media (container create) -> 200 {"id": "container_1"}
    GET /{container}                -> statuses in order, then 200 {"id": "media_final"}
    POST /media_publish             -> logged; returns {"id": "media_final"}
    """
    calls = {"idx": 0}

    def fake_get(url, **kwargs):
        _call_log.append(("GET", url))
        if "/media_publish" in url:
            raise AssertionError("unexpected")
        params = kwargs.get("params") or {}
        if params.get("fields") == "status_code":
            # Container status poll: GET /{container_id}?fields=status_code
            idx = min(calls["idx"], len(statuses) - 1)
            calls["idx"] += 1
            return _make_container_status_response(statuses[idx])
        if url.endswith("/media"):
            # Media container creation: POST-style path handled by fake_post;
            # this branch covers any GET to /{account}/media
            resp = mock.MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "container_1"}
            return resp
        # verify_credentials / insights etc
        resp = mock.MagicMock()
        resp.json.return_value = {"id": "ig_account_id", "username": "laggaye_broo", "media_count": 0}
        return resp

    def fake_post(url, **kwargs):
        _call_log.append(("POST", url))
        resp = mock.MagicMock()
        resp.status_code = 200
        if "/media_publish" in url:
            resp.json.return_value = {"id": "media_final"}
        else:
            resp.json.return_value = {"id": "container_1"}
        return resp

    return mock.patch("app.publisher.graph_api.requests.get", side_effect=fake_get), \
        mock.patch("app.publisher.graph_api.requests.post", side_effect=fake_post)


def _run_publish_with(statuses, gate=True, token="valid_token", limit_ts=None):
    """Run the live publish path with mocked network. gate=False opens the
    ENABLE_LIVE_INSTAGRAM_PUBLISH gate for this run only."""
    patchers = []
    if gate:
        patchers.append(mock.patch.object(config, "enable_live_instagram_publish", True))
    patchers.append(mock.patch.object(config, "mock_mode", False))
    patchers.append(mock.patch.object(
        config.active_account, "ig_account_id", "ig_account_id"))
    patchers.append(mock.patch.object(
        config.active_account, "ig_access_token", token))
    g, p = _mock_requests_with_status_sequence(statuses)
    patchers.extend((g, p))
    for pt in patchers:
        pt.start()
    try:
        publisher = GraphAPIPublisher()
        content = mock.MagicMock()
        content.caption = "test caption"
        content.hashtags = ["#test"]
        content.drive_file_ids = {"public_url": "https://example.com/meme.jpg"}
        # Blocker 3 validators: treat the mock URL as valid unless the test
        # patches validate_image_url itself (T7-T9 do).
        return publisher.publish_now(content)
    finally:
        for pt in reversed(patchers):
            pt.stop()


# ---------------------------------------------------------------------------
# Blocker 1 — container readiness polling
# ---------------------------------------------------------------------------

@check("B1-1 Container FINISHED -> publish allowed in mock mode")
def t1_finished():
    with mock.patch("app.publisher.publisher._rate_limiter") as rl:
        rl.can_publish.return_value = (True, "")
        with mock.patch("app.publisher.publisher.validate_image_url"):
            result = _run_publish_with(["FINISHED"])
    assert result.success is True, f"expected success, got {result}"
    assert result.instagram_post_id == "media_final", f"post id mismatch: {result}"
    urls = [u for _, u in _call_log]
    assert len(urls) >= 4, f"expected 4+ API calls, got {len(urls)}: {urls}"
    assert any("/media_publish" in u for u in urls), f"media_publish never called; log={_call_log}"
    # Sequence must be: verify -> create container -> status poll -> publish.
    assert urls[1].endswith("/media"), f"second call should be container creation: {urls}"
    assert urls[2].endswith("/container_1"), f"third call should be status poll: {urls}"


@check("B1-2 Container PROCESSING -> polling continues until FINISHED")
def t2_processing():
    with mock.patch("app.publisher.publisher._rate_limiter") as rl:
        rl.can_publish.return_value = (True, "")
        with mock.patch("app.publisher.publisher.validate_image_url"):
            with mock.patch("app.publisher.graph_api.time.sleep") as sleep:
                result = _run_publish_with(["PROCESSING", "PROCESSING", "FINISHED"])
    assert sleep.call_count >= 2, f"expected >=2 sleeps during polling, got {sleep.call_count}"
    assert result.success is True, result
    assert any("/media_publish" in u for _, u in _call_log), "publish never happened"


@check("B1-3 Container ERROR -> publish blocked")
def t3_error():
    with mock.patch("app.publisher.publisher._rate_limiter") as rl:
        rl.can_publish.return_value = (True, "")
        with mock.patch("app.publisher.publisher.validate_image_url"):
            result = _run_publish_with(["ERROR"])
    assert result.success is False
    assert "ERROR" in result.error
    assert not any("/media_publish" in u for _, u in _call_log), "media_publish called despite ERROR"


@check("B1-4 Container EXPIRED -> publish blocked")
def t4_expired():
    with mock.patch("app.publisher.publisher._rate_limiter") as rl:
        rl.can_publish.return_value = (True, "")
        with mock.patch("app.publisher.publisher.validate_image_url"):
            result = _run_publish_with(["EXPIRED"])
    assert result.success is False
    assert "EXPIRED" in result.error
    assert not any("/media_publish" in u for _, u in _call_log), "media_publish called despite EXPIRED"


@check("B1-5 30-second timeout -> publish blocked")
def t5_timeout():
    """Client polls forever; with mocked FINISHED-less statuses and real sleep
    patched to 0.01s, the 30s hard timeout must fire quickly."""
    with mock.patch("app.publisher.publisher._rate_limiter") as rl:
        rl.can_publish.return_value = (True, "")
        with mock.patch("app.publisher.publisher.validate_image_url"):
            with mock.patch("app.publisher.graph_api.time.sleep", return_value=None):
                with mock.patch("app.publisher.graph_api.time.time",
                                side_effect=iter([0.0, 31.0, 31.1])):
                    result = _run_publish_with(["PROCESSING", "PROCESSING", "PROCESSING"])
    assert result.success is False
    assert "FINISHED" in result.error or "timeout" in result.error.lower() or "30" in result.error
    assert not any("/media_publish" in u for _, u in _call_log), "media_publish called despite timeout"


# ---------------------------------------------------------------------------
# Blocker 2 — hard live-publish safety gate
# ---------------------------------------------------------------------------

@check("B2-6 ENABLE_LIVE_INSTAGRAM_PUBLISH=false -> no live API call")
def t6_gate_closed():
    with mock.patch.object(config, "enable_live_instagram_publish", False):
        with mock.patch.object(config, "mock_mode", False):
            publisher = GraphAPIPublisher()
            content = mock.MagicMock()
            content.caption = "x"
            content.hashtags = []
            content.drive_file_ids = {"public_url": "https://example.com/m.jpg"}
            result = publisher.publish_now(content)
    assert result.success is False
    assert "DISABLED" in result.error
    assert len(_call_log) == 0, f"live API call made with gate closed: {_call_log}"


# ---------------------------------------------------------------------------
# Blocker 3 — image URL validation
# ---------------------------------------------------------------------------

@check("B3-7 Invalid/private image URL -> blocked")
def t7_invalid_url():
    with mock.patch("requests.head") as head, mock.patch("requests.get") as get:
        head.side_effect = requests.ConnectionError("private network")
        get.side_effect = requests.ConnectionError("private network")
        try:
            validate_image_url("https://169.254.169.254/secret")
        except ValueError as e:
            assert "not be reached" in str(e) or "not a public" in str(e)
            return
        raise AssertionError("validate_image_url did not reject an unreachable URL")


@check("B3-8 Wrong content type -> blocked")
def t8_bad_type():
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": "500"}
    with mock.patch("requests.head", return_value=resp):
        try:
            validate_image_url("https://example.com/not-an-image")
        except ValueError as e:
            assert "Content-Type" in str(e) or "JPEG/PNG" in str(e)
            return
        raise AssertionError("validate_image_url did not reject text/html")


@check("B3-9 Image > 8 MB -> blocked")
def t9_too_big():
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "image/jpeg", "Content-Length": str(9 * 1024 * 1024)}
    with mock.patch("requests.head", return_value=resp):
        try:
            validate_image_url("https://example.com/huge.jpg")
        except ValueError as e:
            assert "8 MB" in str(e)
            return
        raise AssertionError("validate_image_url did not reject a 9 MB image")


# ---------------------------------------------------------------------------
# Blocker 4 — token validation
# ---------------------------------------------------------------------------

@check("B4-10 Missing/invalid credentials -> blocked")
def t10_bad_creds():
    with mock.patch.object(config, "enable_live_instagram_publish", True):
        with mock.patch.object(config, "mock_mode", False):
            with mock.patch.object(
                config.active_account, "ig_account_id", ""):
                with mock.patch.object(
                    config.active_account, "ig_access_token", ""):
                    publisher = GraphAPIPublisher()
                    content = mock.MagicMock()
                    content.caption = "x"
                    content.hashtags = []
                    content.drive_file_ids = {}
                    try:
                        result = publisher.publish_now(content)
                    except RuntimeError as e:
                        # require_live_credentials raises loudly — safe failure,
                        # exactly the design (no API call is made)
                        assert "not set" in str(e) or "MOCK_MODE" in str(e)
                        assert len(_call_log) == 0, "live API call made with missing credentials"
                        return
    assert result.success is False
    assert "not set" in result.error or "Credentials" in result.error or "MOCK_MODE" in result.error
    assert len(_call_log) == 0, "live API call made with missing credentials"


# ---------------------------------------------------------------------------
# Blocker 5 — rolling 24h rate limit
# ---------------------------------------------------------------------------

@check("B5-11 Rate limit >= 15 -> blocked")
def t11_rate_limit():
    log_file = Path("/tmp/publish_log_test.json")
    now = time.time()
    timestamps = [now - 3600] * 15  # 15 publishes within 24h
    with open(str(log_file), "w") as f:
        json.dump(timestamps, f)
    limiter = PublishRateLimiter(log_file)
    allowed, reason = limiter.can_publish(now=now)
    assert allowed is False, f"expected refusal at 15 publishes, got allowed"
    assert "limit" in reason.lower()
    # Confirm publishing refusal through the full publisher path too:
    with mock.patch.object(config, "enable_live_instagram_publish", True):
        with mock.patch.object(config, "mock_mode", False):
            with mock.patch("app.publisher.publisher._rate_limiter", limiter):
                with mock.patch("app.config.config.require_live_credentials"):
                    with mock.patch.object(
                        InstagramGraphAPIClient, "verify_credentials"):
                        with mock.patch("app.publisher.publisher.validate_image_url"):
                            publisher = GraphAPIPublisher()
                            content = mock.MagicMock()
                            content.caption = "x"
                            content.hashtags = []
                            content.drive_file_ids = {"public_url": "https://example.com/m.jpg"}
                            result = publisher.publish_now(content)
    assert result.success is False, f"expected refusal, got {result}"
    assert "limit" in result.error.lower(), f"expected rate-limit reason, got: {result.error}"
    assert not any("/media" in u or "/media_publish" in u for _, u in _call_log)
    os.remove(log_file)


# ---------------------------------------------------------------------------
# B12 — existing P0 behavior intact
# ---------------------------------------------------------------------------

@check("B12 Existing P0 behavior intact (publisher contract + default gates)")
def t12_p0_intact():
    # Default gates are closed (mock mode on, live publish off)
    assert config.mock_mode is True
    assert config.enable_live_instagram_publish is False
    # Publisher still satisfies its interface (mock publish works)
    publisher = GraphAPIPublisher()
    content = mock.MagicMock()
    content.caption = "x"
    content.hashtags = ["#t"]
    result = publisher.publish_now(content)
    assert result.success is True
    assert result.instagram_post_id.startswith("mock_")
    # Rate limiter works on a temp log file
    limiter = PublishRateLimiter(log_path=Path("/tmp/publish_log_p0test.json"))
    ok, reason = limiter.can_publish(now=0)
    assert ok is True
    assert reason == ""


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import re as _re
    for name in sorted(globals()):
        if _re.match(r"^t\d", name) and callable(globals()[name]):
            globals()[name]()
    print("P2 BLOCKERS SUITE")
    for name, status, detail in results:
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"RESULT: {passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
