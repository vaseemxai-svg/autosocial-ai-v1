"""One-off functional check for the shared WEB_API_SECRET auth gate.

Covers BOTH protected routes: /generate and /post-now (same helper,
same source of truth — config.web_api_secret).

Run inside Docker:
    docker compose exec autosocial-ai python tests/auth_gate_check.py

If WEB_API_SECRET is empty, the gate is inactive (localhost-only default)
and the check reports that instead.
"""
import os
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
SECRET = os.environ.get("WEB_API_SECRET", "").strip()

# NoRedirect opener: captures the RAW status a route returns (302 redirect,
# 401 rejection) instead of following redirects to the final 200 page.
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

_opener = urllib.request.build_opener(_NoRedirect)


def hit(path, auth=None, method="POST"):
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    try:
        return _opener.open(req, timeout=10).status
    except urllib.error.HTTPError as exc:
        return exc.code

def warm_queue():
    """Fill the queue so /post-now can succeed (index GET auto-generates)."""
    urllib.request.urlopen(f"{BASE}/", timeout=10)

if not SECRET:
    print("WEB_API_SECRET is empty — auth gate inactive (localhost-only default)")
    print("AUTH GATE: NO ASSERTION POSSIBLE WITH GATE DISABLED")
    sys.exit(0)

warm_queue()

checks = [
    # /generate — new mandatory auth
    ("generate: no header rejected", 401, hit("/generate", None)),
    ("generate: wrong secret rejected", 401, hit("/generate", "totally-wrong-secret")),
    ("generate: correct secret accepted", 302, hit("/generate", SECRET)),
    # /post-now — existing behavior preserved
    ("post-now: no header rejected", 401, hit("/post-now", None)),
    ("post-now: wrong secret rejected", 401, hit("/post-now", "totally-wrong-secret")),
    ("post-now: correct secret accepted", 200, hit("/post-now", SECRET)),
]

ok = True
for label, expect, got in checks:
    passed = got == expect
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] {label} (expect {expect}, got {got})")

print("AUTH GATE: " + ("ALL CHECKS PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
