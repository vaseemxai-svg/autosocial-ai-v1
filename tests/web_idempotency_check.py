"""Web-layer idempotency verification against the RUNNING server.

- First POST /post-now -> mock publish succeeds (item posted).
- Same item second POST /post-now -> blocked: success=false,
  "Nothing queued to post" (item was removed after the first success).

MOCK_MODE=true is passed via -e so the running live-credential server
switches to mock mode for this test only. Zero live Meta calls.
"""
import json
import os
import sys

sys.path.insert(0, '/app')
import tempfile
import urllib.error
import urllib.request

BASE = 'http://localhost:8000'

# Start from a clean rate-limit counter (previous unit test filled the
# shared publish_log.json up to the 15-post limit).
import app.config as _cfg  # noqa: E402
import app.publisher.publisher as _pub  # noqa: E402

_tmp = tempfile.NamedTemporaryFile(prefix='publish_log_', suffix='.json',
                                   delete=False)
_tmp.close()
_pub._rate_limiter._log_path = _cfg.config.local_logs_dir / os.path.basename(_tmp.name)
if _pub._rate_limiter._log_path.exists():
    _pub._rate_limiter._log_path.unlink()
SECRET = os.environ.get('WEB_API_SECRET', '')

passed = []


def hit(path):
    req = urllib.request.Request(
        BASE + path, data=b'{}', method='POST',
        headers={'Content-Type': 'application/json'})
    if SECRET:
        req.add_header('Authorization', f'Bearer {SECRET}')
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return exc.code, json.load(exc)


# Warm the queue (index GET auto-generates one item in mock mode)
urllib.request.urlopen(BASE + '/', timeout=30)

st1, j1 = hit('/post-now')
print('1st POST /post-now ->', st1, j1)
ok1 = st1 == 200 and j1.get('success') is True

st2, j2 = hit('/post-now')
print('2nd POST /post-now ->', st2, j2)
ok2 = (st2 == 400 and 'Nothing queued' in j2.get('error', ''))

tag1 = 'PASS' if ok1 else 'FAIL'
tag2 = 'PASS' if ok2 else 'FAIL'
print(f'[{tag1}] First Post Now -> item publishes')
print(f'[{tag2}] Same item second time -> blocked (no second publish)')
ok = ok1 and ok2
print('WEB-LAYER IDEMPOTENCY:', 'VERIFIED' if ok else 'FAILED')
raise SystemExit(0 if ok else 1)
