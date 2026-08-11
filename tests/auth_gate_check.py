"""One-off functional check for the /post-now WEB_API_SECRET auth gate.

Run inside Docker:
    docker compose exec -e WEB_API_SECRET=<value> autosocial-ai python tests/auth_gate_check.py

If WEB_API_SECRET is empty/unset in the env, the gate is inactive
(localhost-only default) and the check reports that instead.
"""
import os
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"


def post_now(auth=None):
    req = urllib.request.Request(f"{BASE}/post-now", method="POST")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    try:
        return urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as exc:
        return exc.code


def warm_queue():
    urllib.request.urlopen(f"{BASE}/", timeout=10)


secret = os.environ.get("WEB_API_SECRET", "").strip()
if not secret:
    print("WEB_API_SECRET is empty — auth gate inactive (localhost-only default)")
    print("PASS (no assertion possible with gate disabled)")
    sys.exit(0)

warm_queue()

checks = [
    ("no Authorization header rejected", 401, post_now(None)),
    ("wrong secret rejected", 401, post_now("totally-wrong-secret")),
    ("correct secret accepted", 200, post_now(secret)),
]

ok = True
for label, expect, got in checks:
    passed = got == expect
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] {label} (expect {expect}, got {got})")

print("AUTH GATE: " + ("ALL CHECKS PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
