"""Shared test helpers for the AutoSocial AI test suites.

ONE helper for auth: every test request that hits a protected route MUST use
`authed_request()` so that the behaviour of `WEB_API_SECRET` is exercised
consistently across all suites. The secret itself is read from
`config.web_api_secret` in the server — this module reads the same env var
(the client side of the same gate), so there is still only ONE auth system.
"""
import os
import urllib.request


def _secret() -> str:
    return os.getenv("WEB_API_SECRET", "").strip()


def authed_request(url, method="POST", data=None, timeout=10):
    """Build+send a request, attaching the Bearer header if a secret is set."""
    req = urllib.request.Request(url, method=method, data=data)
    secret = _secret()
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    return urllib.request.urlopen(req, timeout=timeout)
