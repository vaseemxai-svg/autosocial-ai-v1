# Self-Audit Notes (internal)

## Test re-verification (Docker, MOCK_MODE=true)
- P0 suite: 7/7 PASS
- Day-1 suite: 5/5 PASS
- Repo clean at commit ea81edb (only untracked DAY1_REPORT.md, a report artifact)
- Container env: MOCK_MODE=true

## Meta API cross-check (official docs)
1. media_publish endpoint: POST /{ig-user-id}/media_publish?creation_id={id}&access_token={token}
   - Our code: MATCHES exactly (v19.0 host graph.facebook.com, data={creation_id, access_token})
2. media container endpoint: POST /{ig-user-id}/media with image_url + caption + access_token
   - Docs: image_url or video_url + caption optional, access_token required — MATCHES
3. Verify endpoint: GET /{ig-user-id}?fields=id,username,media_count — standard IG-User reading call, valid; NO write
4. Docs notes:
   - Containers expire after 24h; 400 containers/24h limit; 50 publishes/24h; JPEG only; image max 8MB, 320-1440px, 4:5 to 1.91:1
   - "We cURL media used in publishing attempts, so the media must be hosted on a publicly accessible server" — Drive share link works IF publicly viewable (link Anyone-with-link)
   - Known issue: some Drive links no longer accepted by IG API (Reddit thread) — our Drive uploader sets public share link but IG may reject Google Drive-hosted images (CURL error). MITIGATION NEEDED: host image on app's own web server (serve_image route exists!) OR download-then-host. Document as known risk R3.
   - URL should be US-ASCII (our caption/hashtags may have non-ASCII — requests library URL-encodes body params, fine; but advise ASCII captions)
   - Permission required: instagram_content_publish + instagram_basic; token must be User token, MANAGE/CREATE_CONTENT tasks on connected Page
   - PPA (Page Publishing Authorization) and 2FA checks apply
   - API v19.0 in our code is valid (supported); v26.0 latest per docs — worth noting upgrade later but not now (freeze)

## verify_credentials() safety analysis
- Only method called: requests.GET on /{ig-user-id} — purely read; Meta classifies this as a "Reading" operation
- Cannot create container/post by construction: no POST, no media endpoint, response parsed for "id" but never used to call publish
- Mock mode: returns early, no network at all
- Error path raises InstagramGraphAPIError — never proceeds to publish

## Credential handling security audit findings
- Credentials: env vars only (IG_ACCOUNT_ID, IG_ACCESS_TOKEN via .env / docker-compose), never in code, scanned clean
- .env.example committed (blank values), .env gitignored ✓
- .env is NOT baked into image? — docker-compose env_file usage? Need to verify compose uses env_file and volume-mounts .env (not copy) — check docker-compose.yml env section
- access_token sent as POST body param — acceptable per Meta docs (supports Bearer header too); body transfer over TLS
- No secrets in logs (verify) — grep logs for token patterns
- Google service account JSON: volume mount, never baked into image ✓; stored in Drive via _live_upload (Drive side)

## TODO for report
- git diff (ea81edb vs ea81edb — working tree identical to HEAD; diff = previous commit range or file-level listing)
- files changed list: graph_api.py, server.py, drive_uploader.py, CHANGELOG.md (+2 test files created)
- risks list (from doc findings + our analysis)
