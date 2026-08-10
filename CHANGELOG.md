# Changelog

All notable changes to AutoSocial AI are documented in this file.

## [1.0.3] — Day 1: Instagram publishing readiness + P0 fixes

### Added
- `InstagramGraphAPIClient.verify_credentials()`: official `GET /{ig-user-id}`
  pre-publish auth check — verifies token + account ID **without creating any
  media container or post**.
- `POST /verify-credentials` web route: runs the pre-publish check from the UI.

### Fixed
- `_build_drive_service()` now rejects a **directory** at the service-account
  path with a clear RuntimeError (a broken bind mount used to leak a raw
  `IsADirectoryError`).
- Test harness attaches its logging capture handler **before** any app import
  and sets root level to DEBUG — matches how the production server configures
  the root logger via `basicConfig`.

### Tested (inside Docker)
- P0 suite 7/7 pass; Day-1 suite 5/5 pass (mock-only, zero live Instagram
  calls, zero media containers created).

## [1.0.2] — 2026-08-08 — Developer (Manus)

### Added
- **Live Drive upload** (`app/storage/drive_uploader.py`): completed `_live_upload()` using `google-api-python-client` with service-account auth. Uploads image → `Generated_Memes/`, caption → `Captions/`, hashtags → `Hashtags/` under the configured root folder. Auto-creates missing folders (idempotent). Returns a public share URL so the publisher can pass it to the Graph API.
- **Trend collector** (`app/trend_collector/collector.py`): implemented `get_collector()` with two modes selectable via `TREND_COLLECTOR_MODE` env var:
  - `MOCK_DEFAULT` — deterministic best-first ordering (default, good for tests)
  - `RANDOMISED` — weighted random ordering (daily variety between the two slots)
- **Composition root** (`app/main.py`): single wiring point per the architecture docs — concrete classes are instantiated here only; every other module imports ABC interfaces.
- **Docker support**: `Dockerfile` (python:3.11-slim, non-root user) + `docker-compose.yml` (env_file, service-account volume, persistent output volume, healthcheck).
- **`.env.example`**: all env vars documented with setup instructions.

### Verified
- Full pipeline smoke test (collector → generator → storage → queue): PASS
- Flask web server (`/`, `/generate`, `/post-now` routes) in mock mode: PASS — real publish never happens without the human pressing Post Now.

## [1.0.1] — 2026-08-06 — CTO (Claude)

### Added
- Core architecture: `app/interfaces.py` (ABC interfaces + dataclasses), `app/config.py` (centralized `.env` reading).
- Five modules with clean interfaces: `trend_collector`, `content_generator`, `scheduler`, `publisher`, `analytics` (interfaces).
- Official Graph API client (`app/publisher/graph_api.py`) — no browser automation, no credential storage.
- Local-first storage design (`LocalFirstDriveStorage`): validate locally, upload to Drive as a second step; failures never invalidate local content.
- Flask review UI (`app/web/server.py`, `preview.html`) with the single `/post-now` route as the only path to a real post.
- Scheduler generates content only — structurally cannot publish.
- Mock mode everywhere (default `MOCK_MODE=true`).

## [1.0.0] — 2026-08-05

- Project scaffolded. Company formation: Founder (Vaseem), CTO (Claude), Developer (Manus).
