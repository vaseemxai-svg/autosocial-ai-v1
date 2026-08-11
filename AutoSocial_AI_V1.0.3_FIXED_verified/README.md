# AutoSocial AI — Instagram Meme Automation Engine

**Daily Hinglish memes for @laggaye_broo — generated at 9 AM and 7 PM, posted only when you approve.**

| | |
|---|---|
| Version | 1.0.2 |
| License | MIT |
| Instagram | [@laggaye_broo](https://www.instagram.com/laggaye_broo) |
| Company | AutoSocial AI (Founder: Vaseem, CTO: Claude, Developer: Manus) |
| Central storage | [Google Drive — AutoSocial AI](https://drive.google.com/drive/folders/1XpGs0_l_RBcCHAj3O3wO3diavtcRnNt6) |

## One-line Summary

A local-first content engine: a scheduler generates meme topics and images,
queues them for human review in a web UI, and the **only** path to a real
Instagram post is a "Post Now" button. Nothing ever publishes automatically.

## 5-Minute Setup

```bash
# 1. Clone & configure
git clone https://github.com/vaseemxai-svg/autosocial-ai-v1.git
cd autosocial-ai-v1
cp .env.example .env          # MOCK_MODE=true by default — safe to run immediately

# 2. One-command start (Docker)
docker compose up --build -d

# 3. Open the review UI
open http://localhost:8000
```

That's it. In mock mode (default) the pipeline runs fully offline: topics are
pulled from the bundled list, memes are generated, and "Post Now" returns a
mock Instagram post ID without touching Instagram.

### Manual (non-Docker) alternative

```bash
pip install -r requirements.txt
python -m app.main            # Flask UI on http://localhost:8000
```

## How a Post Happens

1. Scheduler runs at `GENERATION_TIMES` (default `09:00,19:00` IST) and queues one topic.
2. A meme image (1080×1080), caption, and hashtags are generated locally.
3. Content is validated locally, then uploaded to Google Drive (mock mode logs instead).
4. You open `http://localhost:8000`, review the card, and either **Regenerate** or **Post Now**.
5. Post Now → Drive public URL → Instagram Graph API two-step publish (`media` → `media_publish`).

## `.env` Reference

| Variable | Purpose | Default |
|---|---|---|
| `MOCK_MODE` | `true` = offline, no Instagram | `true` |
| `IG_USERNAME` | Page handle (display) | `laggaye_broo` |
| `IG_ACCOUNT_ID` | Instagram Business numeric ID | — |
| `IG_ACCESS_TOKEN` | Long-lived Graph API token | — |
| `GOOGLE_DRIVE_FOLDER_ID` | Root Drive folder for outputs | company folder |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | Service account JSON key | `./config/service_account.json` |
| `GENERATION_TIMES` | Comma-separated 24h slots | `09:00,19:00` |
| `TIMEZONE` | Timezone for generation slots | `Asia/Kolkata` |
| `TREND_COLLECTOR_MODE` | `MOCK_DEFAULT` / `RANDOMISED` | `MOCK_DEFAULT` |
| `WEB_HOST` / `WEB_PORT` | Flask bind | `0.0.0.0` / `8000` |

### Going live (MOCK_MODE=false)

1. **Instagram**: Meta Developer Console → Instagram Graph API → grant
   `instagram_basic`, `instagram_content_publish`, `pages_manage_posts` → set
   `IG_ACCOUNT_ID` and a long-lived `IG_ACCESS_TOKEN`.
2. **Drive**: Google Cloud Console → create service account → download JSON
   key → share the Drive root folder with the service account email (Editor)
   → set `GOOGLE_DRIVE_FOLDER_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`.

## Project Layout

```
autosocial-ai-v1/
├── app/
│   ├── interfaces.py            # ABCs + dataclasses (Topic, GeneratedContent, ...)
│   ├── config.py                # Centralized .env reading
│   ├── main.py                  # Composition root — the only wiring point
│   ├── trend_collector/         # get_topics() — V1: bundled mock topics
│   ├── content_generator/       # generate() — caption + PIL meme image
│   ├── scheduler/               # Cron jobs — queues content, CANNOT publish
│   ├── publisher/               # publish_now() — ONLY via /post-now route
│   │   └── graph_api.py         # Official Graph API client (no browser automation)
│   ├── storage/
│   │   └── drive_uploader.py    # Local-first: validate → upload to Drive
│   └── web/                     # Flask review UI + preview.html
├── mock_data/sample_trends.json
├── config/service_account.json  # (gitignored)
├── output/memes/                # (gitignored) persisted by Docker volume
├── docs/architecture.md
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── CHANGELOG.md
└── LICENSE
```

## Safety Guarantees

- **Human-in-the-loop**: the scheduler never imports the publisher — publishing
  is structurally impossible without the button.
- **Local-first**: generation and preview never depend on Drive or Instagram.
- **No secrets in code**: everything lives in `.env` / service-account JSON.
- **Idempotent uploads**: re-runs never duplicate Drive folders; half-uploads
  are impossible (failures raise, caller retries).

## CTO Review Status

| Item | Status |
|---|---|
| CTO v1.0.1 skeleton | Approved for Beta |
| Live Drive upload (`_live_upload()`) | Implemented + verified in mock mode |
| Trend collector (`get_collector()`) | Implemented (MOCK_DEFAULT + RANDOMISED) |
| Docker one-command startup | Tested — `docker compose up --build` works |
| Live Instagram test publish | Pending human credentials (needs owner's IG token) |
| Production approval | Awaiting CTO v1.0.3 review |

## Team & Roles

The Founder (Vaseem) owns the vision and client decisions; the CTO (Claude)
owns architecture, code review, and production approval; the Developer (Manus)
implements features, fixes bugs, and writes documentation. Nothing ships to
production without CTO's "Approved for Production" verdict.
