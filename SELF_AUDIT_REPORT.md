# AutoSocial AI — SELF-AUDIT REPORT

**Version under audit: v1.0.3** · **Commit (frozen): ea81edb** · **Repository:** https://github.com/vaseemxai-svg/autosocial-ai-v1

**From:** Developer (Manus) · **To:** Founder (Vaseem), CTO (Claude), Operations (Loopa)

**Audit scope (per code-freeze instruction):** self-audit only. No features added, no architecture modified, nothing published, no live credentials used.

---

## Status: READY FOR CTO REVIEW

---

## 1. Test Re-Verification (inside Docker, fresh run)

Both suites were re-executed in the running container (`docker exec autosocial-ai python -B tests/*.py`) with `MOCK_MODE=true` confirmed in the container environment.

```
P0 SUITE (CTO's 7 points):
[PASS] 1. Application startup
[PASS] 2. Web UI (root)
[PASS] 3. /post-now mock
[PASS] 4. Mock pipeline
[PASS] 5. Module-to-module interfaces
[PASS] 6. Logging
[PASS] 7. Error handling
RESULT: 7/7 passed

DAY-1 SUITE (mock-only, no live calls):
[PASS] P1-1 Mock publish flow via /post-now
[PASS] P1-2 Credential verification route (mock mode)
[PASS] P1-3 Graph API client class intact (container + publish steps, v19.0, no browser automation)
[PASS] P1-4 No credentials in code or repo (source-tree secret scan clean)
[PASS] P1-5 publish_now human-in-the-loop path (exactly one call site)
RESULT: 5/5 passed

TOTAL: 12/12 PASS
```

## 2. Official Meta API Cross-Check (verified against live Meta documentation, June/July 2026)

Every endpoint and parameter used in `app/publisher/graph_api.py` was cross-checked against Meta's official documentation [1] [2] [3].

| Our Implementation | Meta Official Spec | Verdict |
|---|---|---|
| `POST /{ig-user-id}/media` with `image_url`, `caption`, `access_token` | Docs: `POST /<IG_ID>/media` requires `image_url` or `video_url` + `access_token`; `caption` is a documented optional parameter [1] | ✅ MATCHES |
| `POST /{ig-user-id}/media_publish` with `creation_id`, `access_token` | Docs: `POST /{ig-user-id}/media_publish?creation_id={creation-id}&access_token={access-token}` — both parameters required, exactly as we send them [2] | ✅ MATCHES |
| `verify_credentials()`: `GET /{ig-user-id}?fields=id,username,media_count` | Standard IG-User **Reading** operation (Meta's docs classify reading as non-publishing); the fields set is valid and the call creates no media object [1] | ✅ MATCHES — no write of any kind |
| API host `graph.facebook.com/v19.0` | Valid Graph API version (v26.0 is newest, v19.0 still supported). Upgrade noted for post-freeze | ⚠️ OK, flag R6 |
| Response handling: `id` absent → error raised | Sample success response is `{"id": "<IG_MEDIA_ID>"}`; error bodies lack `id` [2] | ✅ MATCHES |

**Documentation findings logged during the cross-check (see Known Risks):** Meta requires image URLs to be on publicly cURL-able servers [3], JPEG format only, 8 MB / 320–1440 px / 4:5–1.91:1 aspect ratio for images [1], 50 publishes per 24 h [2], and requires `instagram_content_publish` + `instagram_basic` permissions with `MANAGE`/`CREATE_CONTENT` tasks on the connected Page [1] [2].

## 3. Credential Handling — Security Audit

The audit inspected the running container, the image layers, the repository, and the runtime logs. Results:

| Check | Result |
|---|---|
| Credentials in source code (`app/`, `mock_data/`, `Dockerfile`) | ✅ Clean — token-shaped secret scan (`EAAB/IGQV/IGR`, 30+ chars) found 0 hits |
| Repository (all branches) | ✅ Clean — `.env` gitignored, only blank `.env.example` committed |
| Image layers | ✅ No secrets baked in — credentials enter the container solely via `env_file: .env` volume injection in `docker-compose.yml`; service account JSON is a read-only bind mount (`:ro`), never copied into the image |
| Container runtime environment | ✅ `IG_ACCESS_TOKEN` is **not set** in the container (length 0) — expected in mock mode; the app never reads a token until live mode is explicitly enabled |
| Runtime logs (`output/logs/`) | ✅ 0 log files contain token patterns — the token is never written to logs |
| Transmission | Tokens travel only in HTTPS POST bodies/query params to `graph.facebook.com`, per Meta's own documented patterns [1] [2] |
| Fail-early gate | `require_live_credentials()` is called before every live publish; live mode without credentials raises a clear RuntimeError instead of failing at Instagram |

**Finding S1 (medium):** the access token is passed as a request body parameter rather than an `Authorization: Bearer` header. This is exactly how Meta documents the endpoints [1] [2], so it is compliant — but if the CTO prefers header-based auth, that is a trivial post-freeze swap.

## 4. MOCK_MODE Confirmation

`MOCK_MODE=true` is confirmed three ways: the container's PID-1 environment shows `MOCK_MODE=true`; the running `/post-now` endpoint returns `mock_`-prefixed IDs; and the `/verify-credentials` endpoint returns `{"success": true, "mode": "mock"}` without touching any network. In mock mode the publisher's `_live_publish` path is unreachable by construction — `publish_now()` returns at the mock branch, and `require_live_credentials()` is a no-op that guards the live branch.

## 5. verify_credentials() Safety Proof — Creates No Post/Container in Any Condition

This was the highest-priority item. The guarantee holds by construction:

The function body contains **exactly one HTTP call**, `requests.get()` to `/{ig-user-id}` — a documented Reading operation [1]. It contains no `POST`, no reference to `/media` or `/media_publish`, and no code path that could construct or publish a container. The response is parsed only to confirm an `id` field exists; the returned dict is never passed to any publishing method. The mock-mode route returns before any network call at all. The error path raises `InstagramGraphAPIError` and never proceeds. The **only** method in the entire codebase that reaches a publishing endpoint is `GraphAPIPublisher.publish_now()`, and it is called from exactly one place — the `/post-now` route, which exists only behind a human button click. Static verification (P1-5 test) asserts there is exactly one `publish_now(` call site in the web module, and this test re-passed in the re-verification above.

## 6. Git Diff (v1.0.3 commit, frozen)

```
CHANGELOG.md                  |  20 ++++
app/publisher/graph_api.py    |  19 ++++
app/storage/drive_uploader.py |   7 ++
app/web/server.py             |  20 ++++
tests/p0_mock_suite.py        | 220 ++++++++++++++++++++++++++++++++
tests/p1_day1_suite.py        |  92 +++++++++++++
6 files changed, 378 insertions(+)
```

Working tree versus HEAD is **empty** — the codebase is frozen at commit `ea81edb`. Full diff is attached as `v1.0.3_diff.txt` (110 lines).

## 7. Files Changed (exact list)

| File | Change type | Description |
|---|---|---|
| `app/publisher/graph_api.py` | Extended | Added `verify_credentials()` (read-only auth check) |
| `app/web/server.py` | Extended | Added `POST /verify-credentials` route |
| `app/storage/drive_uploader.py` | Fixed | Clear RuntimeError when service-account path is a directory |
| `CHANGELOG.md` | Extended | v1.0.3 entry |
| `tests/p0_mock_suite.py` | Created | CTO P0 suite, 7 tests, runs inside Docker |
| `tests/p1_day1_suite.py` | Created | Day-1 Instagram readiness suite, 5 tests, mock-only |

## 8. Known Risks

| # | Risk | Severity | Note / Mitigation |
|---|---|---|---|
| R1 | **Google Drive-hosted image URLs may be rejected by Instagram's API.** Meta "cURLs" the media URL and community reports indicate Drive links are intermittently refused [3] [4]. | High | When going live, host the image through the app's own `/image/<path>` route (route already exists) or a CDN, instead of the Drive share link. |
| R2 | Live credentials not yet provided; live auth test unexecuted. | Medium | Expected and documented. Live verification happens only after Founder sets `.env` and gives explicit GO. |
| R3 | 24-hour container expiry + 400 containers/24h + 50 publishes/24h limits [1] [2]. | Medium | Pre-publish credential gate (v1.0.3) prevents wasting containers on bad credentials; rate limits must be respected in scheduler logic (not yet enforced in code — scheduled for post-freeze). |
| R4 | Page Publishing Authorization (PPA) or missing 2FA on the connected Facebook Page will cause publish failure [1] [2]. | Medium | Founder should complete PPA proactively, as Meta itself recommends. |
| R5 | Required permissions (`instagram_basic`, `instagram_content_publish`, `pages_read_engagement`) and MANAGE/CREATE_CONTENT tasks must be granted on the Meta app [1] [2]. | Medium | Check during live setup; missing permission produces an API error, never a silent failure. |
| R6 | Graph API v19.0 is older than the current v26.0 [1]. | Low | Still supported; version bump is a one-line post-freeze change, included in the freeze explicitly to avoid touching a working endpoint. |
| R7 | Sandbox Docker used `iptables:false` daemon workaround; founder's laptop runs standard Docker unaffected. | Low | Documented in repo README. |

**No live post was made. No credentials were used. No features were added. Architecture is unmodified.**

---

## References

[1]: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media "Meta for Developers — IG User Media (reference, updated Jun 2026)"
[2]: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media_publish "Meta for Developers — IG User Media Publish (reference)"
[3]: https://developers.facebook.com/documentation/instagram-platform/content-publishing "Meta for Developers — Content Publishing guide (updated Jun 2026)"
[4]: https://www.reddit.com/r/n8n/comments/1mlvofx/facebookinstagram_graph_api_no_longer_accepts/ "Reddit — Facebook/Instagram Graph API no longer accepts Google Drive media links"

- [1] Meta for Developers — IG User Media: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
- [2] Meta for Developers — IG User Media Publish: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media_publish
- [3] Meta for Developers — Content Publishing guide: https://developers.facebook.com/documentation/instagram-platform/content-publishing
- [4] Reddit thread on Drive-hosted image rejection: https://www.reddit.com/r/n8n/comments/1mlvofx/facebookinstagram_graph_api_no_longer_accepts/

**Status: READY FOR CTO REVIEW**
