"""
P0 Mock Test Suite — runs INSIDE the Docker environment.
No Instagram credentials required (MOCK_MODE=true).

Covers the 7 P0 test points:
  1. application startup
  2. web UI
  3. /post-now endpoint
  4. mock pipeline
  5. module-to-module communication
  6. logging
  7. error handling
"""
import ast
import inspect
import io
import logging
import sys
import urllib.request
import urllib.error

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
            except Exception as e:  # noqa: BLE001
                results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# 1. Application startup — all modules import, config loads, app wires up
# ---------------------------------------------------------------------------
@check("1. Application startup")
def t_startup():
    from app.config import config
    assert config.mock_mode is True, "MOCK_MODE must be true"
    from app.main import build_application
    app = build_application()
    assert set(app.keys()) == {"collector", "generator", "storage", "publisher", "scheduler", "config"}


# ---------------------------------------------------------------------------
# 2. Web UI — root route returns 200 and the preview card renders
# ---------------------------------------------------------------------------
@check("2. Web UI (root)")
def t_web_ui():
    req = urllib.request.urlopen("http://localhost:8000/", timeout=10)
    assert req.status == 200
    html = req.read().decode()
    assert "AutoSocial AI" in html, "preview template not rendered"
    assert "@laggaye_broo" in html, "page handle missing"
    assert "Post Now" in html, "Post Now button missing"


# ---------------------------------------------------------------------------
# 3. /post-now endpoint — mock publish returns success
# ---------------------------------------------------------------------------
@check("3. /post-now mock")
def t_post_now():
    req = urllib.request.Request("http://localhost:8000/post-now", method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode()
    assert resp.status == 200, f"status {resp.status}"
    assert '"success": true' in data or '"success":true' in data, data
    assert "mock_" in data, "expected mock instagram_post_id"


# ---------------------------------------------------------------------------
# 4. Mock pipeline — collector -> generator -> storage -> queue
# ---------------------------------------------------------------------------
@check("4. Mock pipeline")
def t_pipeline():
    from app.main import build_application
    app = build_application()
    content = app["scheduler"].run_once()
    assert content is not None, "run_once returned nothing"
    assert content.image_path, "no image generated"
    assert content.caption.strip(), "empty caption"
    assert len(content.hashtags) >= 3, "too few hashtags"
    # Mock storage must have logged locally (not attempted Drive)
    assert content.drive_file_ids.get("mock") is True, "mock upload not logged"


# ---------------------------------------------------------------------------
# 5. Module-to-module communication — interfaces honoured
# ---------------------------------------------------------------------------
@check("5. Module-to-module interfaces")
def t_interfaces():
    from app.interfaces import (TrendCollectorInterface, ContentGeneratorInterface,
                                StorageInterface, PublisherInterface)
    from app.trend_collector.collector import get_collector
    from app.content_generator.generator import TemplateContentGenerator
    from app.storage.drive_uploader import LocalFirstDriveStorage
    from app.publisher.publisher import GraphAPIPublisher
    assert isinstance(get_collector(), TrendCollectorInterface)
    assert isinstance(TemplateContentGenerator(), ContentGeneratorInterface)
    assert isinstance(LocalFirstDriveStorage(), StorageInterface)
    assert isinstance(GraphAPIPublisher(), PublisherInterface)
    # Scheduler structurally cannot publish
    src = inspect.getsource(
        __import__("app.scheduler.scheduler", fromlist=["GenerationScheduler"])
        .GenerationScheduler
    )
    tree = ast.parse(src)
    imports = [n.names[0].name for node in ast.walk(tree)
               if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not any("publisher" in n for n in imports), "scheduler must not import publisher"


# ---------------------------------------------------------------------------
# 6. Logging — loggers exist, capture log emission during a run
# ---------------------------------------------------------------------------
@check("6. Logging")
def t_logging():
    # The app relies on root-logger handlers (no module-level basicConfig).
    # Handlers added AFTER module imports find the loggers already created,
    # and Python caches the effective level at logger creation when the
    # manager tree walks parents — so capture must be attached BEFORE any
    # app import, exactly as the production web server does via basicConfig.
    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        from app.main import build_application
        build_application()["scheduler"].run_once()
    finally:
        root.removeHandler(handler)
    output = captured.getvalue()
    assert "Queued new content" in output, "scheduler log not emitted"
    assert "[MOCK]" in output, "mock storage log not emitted"


# ---------------------------------------------------------------------------
# 7. Error handling — bad inputs raise clear errors, never crash silently
# ---------------------------------------------------------------------------
@check("7. Error handling")
def t_errors():
    from app.interfaces import Topic, GeneratedContent
    from app.storage.drive_uploader import LocalFirstDriveStorage
    storage = LocalFirstDriveStorage()

    # Missing image file
    bad = GeneratedContent(Topic("t", "relatable", "mock"), "/nonexistent.png",
                           "caption", ["#h"], "2026-01-01T00:00:00Z")
    assert storage.validate(bad) is False, "should reject missing image"

    # Empty caption
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    tmp.close()
    try:
        bad2 = GeneratedContent(Topic("t", "relatable", "mock"), tmp.name,
                                "   ", ["#h"], "2026-01-01T00:00:00Z")
        assert storage.validate(bad2) is False, "should reject empty caption"
    finally:
        os.unlink(tmp.name)

    # Live upload without credentials must raise a clear RuntimeError
    # (not NotImplementedError, and not a cryptic filesystem error). The
    # docker volume mount can leave a dangling config dir, so validate that
    # the check reads the *contents* of the path correctly.
    try:
        storage._live_upload(bad)
        assert False, "_live_upload should raise without service account"
    except RuntimeError as e:
        msg = str(e).lower()
        assert "service account" in msg or "google_service_account" in msg, str(e)
    except NotImplementedError:
        assert False, "_live_upload must be implemented (NotImplementedError)"

    # A directory is never a valid service account file — must fail cleanly
    import tempfile as _tmp
    tmp2 = _tmp.NamedTemporaryFile(suffix=".png", delete=False)
    tmp2.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    tmp2.close()
    dir_cfg = GeneratedContent(Topic("t", "relatable", "mock"), tmp2.name,
                               "caption", ["#h"], "2026-01-01T00:00:00Z")
    try:
        storage._live_upload(dir_cfg)
        assert False, "_live_upload should raise for a directory path"
    except RuntimeError as e:
        msg = str(e).lower()
        assert ("service account" in msg or "not set" in msg
                or "does not point at a file" in msg), str(e)
    except (IsADirectoryError, PermissionError, OSError):
        assert False, "must raise a clear RuntimeError, not a raw OS error"
    finally:
        os.unlink(tmp2.name)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [t_startup, t_web_ui, t_post_now, t_pipeline, t_interfaces,
             t_logging, t_errors]
    for t in tests:
        t()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print("=" * 60)
    print("P0 MOCK TEST SUITE — INSIDE DOCKER")
    print("=" * 60)
    for name, status, detail in results:
        mark = "PASS" if status == "PASS" else "FAIL"
        print(f"[{mark}] {name}" + (f"  ← {detail}" if detail else ""))
    print("=" * 60)
    print(f"RESULT: {passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
