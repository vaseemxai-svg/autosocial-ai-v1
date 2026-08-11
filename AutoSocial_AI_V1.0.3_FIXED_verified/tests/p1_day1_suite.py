"""P1 Day-1 suite — Instagram publishing readiness (no live publishing).
Runs INSIDE Docker. MOCK_MODE only; never creates an IG media container."""
import json
import sys
import urllib.request

sys.path.insert(0, "/app")

results = []

def check(name):
    def deco(fn):
        def wrapper():
            try:
                fn()
                results.append((name, "PASS", ""))
            except AssertionError as e:
                results.append((name, "FAIL", str(e)))
            except Exception as e:
                results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        return wrapper
    return deco


@check("P1-1 Mock publish flow via /post-now")
def t_mock_publish():
    # /post-now needs a queued item; /generate creates one on demand
    gen = urllib.request.Request("http://localhost:8000/generate", method="POST")
    urllib.request.urlopen(gen, timeout=15).read()
    req = urllib.request.Request("http://localhost:8000/post-now", method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    assert data["success"] is True
    assert data["instagram_post_id"].startswith("mock_")


@check("P1-2 Credential verification route (mock mode)")
def t_verify_mock():
    req = urllib.request.Request("http://localhost:8000/verify-credentials", method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    assert data["success"] is True and data["mode"] == "mock"


@check("P1-3 Graph API client class intact")
def t_client_intact():
    from app.publisher.graph_api import InstagramGraphAPIClient
    import inspect
    src = inspect.getsource(InstagramGraphAPIClient)
    assert "_create_media_container" in src, "media container step missing"
    assert "_publish_container" in src, "publish step missing"
    assert "v19.0" in inspect.getsource(sys.modules["app.publisher.graph_api"])
    # no browser automation anywhere
    assert "selenium" not in src.lower() and "chromium" not in src.lower()


@check("P1-4 No credentials in code or repo")
def t_no_secrets():
    from app.publisher import publisher
    src = inspect.getsource(publisher)
    assert "EAAB" not in src and "IGQV" not in src, "token hardcoded!"
    from app.config import config
    assert len(config.active_account.ig_access_token) == 0, "token must come from .env only"
    # scan the deployed source tree for token-shaped secrets
    import subprocess
    tree = subprocess.run(["grep", "-rIE", "(EAAB|IGQV|IGR)[A-Za-z0-9_-]{60,}",
                           "/app/app", "/app/mock_data", "/app/Dockerfile"],
                          capture_output=True, text=True).stdout
    assert not tree.strip(), f"token-shaped secret found in source:\n{tree}"


@check("P1-5 publish_now human-in-the-loop path")
def t_htl_path():
    from app.web import server
    src = inspect.getsource(server)
    assert "post_now" in src and "/post-now" in src
    # only one publish entry point in the whole web module
    assert src.count("publish_now(") == 1, "multiple publish call sites!"


if __name__ == "__main__":
    import inspect
    [t() for t in (t_mock_publish, t_verify_mock, t_client_intact, t_no_secrets, t_htl_path)]
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print("=" * 60)
    print("P1 DAY-1 INSTAGRAM PUBLISHING SUITE (MOCK ONLY, NO LIVE POST)")
    print("=" * 60)
    for name, status, detail in results:
        print(f"[{status}] {name}" + (f"  ← {detail}" if detail else ""))
    print("=" * 60)
    print(f"RESULT: {passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
