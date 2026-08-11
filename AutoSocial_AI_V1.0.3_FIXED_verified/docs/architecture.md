# AutoSocial AI — Architecture (v1.0.2)

## Design Philosophy

AutoSocial AI is a **local-first content engine** for an Instagram meme page.
The core principle, mandated by the CTO, is:

> Nothing posts to Instagram until a human presses the button. The scheduler
> can generate and queue content, but structurally it cannot publish.

This means the business value compounds safely: even if the app crashes, the
network is down, or a credential is wrong, all generated content remains
valid locally and reviewable in the web UI.

## Module Map

```
                          ┌─────────────────────┐
                          │      .env file       │
                          │  (secrets, mode)     │
                          └─────────┬───────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │       app/config.py            │
                    │  single Config dataclass       │
                    └───────────────┬────────────────┘
                                    │
┌─────────────┐    ┌───────────────▼───────────────────────────────┐
│ Mock topics  │───▶│  TrendCollectorInterface  (get_topics)        │
│ (V1 source) │    │  └─ MockTrendCollector / RandomTrendCollector │
└─────────────┘    └───────────────┬───────────────────────────────┘
                                   │ Topic
                    ┌──────────────▼───────────────────────────────┐
                    │  ContentGeneratorInterface (generate)        │
                    │  └─ TemplateContentGenerator (V1)            │
                    │      → PIL 1080x1080 meme + Hinglish caption │
                    └──────────────┬───────────────────────────────┘
                                   │ GeneratedContent (local file)
                    ┌──────────────▼───────────────────────────────┐
                    │  StorageInterface (validate → upload)        │
                    │  └─ LocalFirstDriveStorage                   │
                    │      validate locally (never fails on Drive) │
                    │      mock: local JSON log                    │
                    │      live: google-api-python-client          │
                    │          image  → Generated_Memes/           │
                    │          caption → Captions/                 │
                    │          hashtags→ Hashtags/                 │
                    └──────────────┬───────────────────────────────┘
                                   │ queue (in-memory)
                    ┌──────────────▼───────────────────────────────┐
                    │  Flask web UI (app/web/server.py)            │
                    │  preview → Regenerate / Post Now             │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ /post-now — THE ONLY publish path      │  │
                    │  └────────────────────────────────────────┘  │
                    └──────────────┬───────────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────────┐
                    │  PublisherInterface (publish_now)            │
                    │  └─ GraphAPIPublisher                        │
                    │      mock: fake instagram_post_id            │
                    │      live: InstagramGraphAPIClient (v19.0)   │
                    │          1. media container (image_url)      │
                    │          2. media_publish                    │
                    └──────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | File | Responsibility | Key invariant |
|---|---|---|---|
| Interfaces | `app/interfaces.py` | ABCs + dataclasses (`Topic`, `GeneratedContent`, `PublishResult`) | All modules import interfaces only, never cross-module concrete classes |
| Config | `app/config.py` | Reads `.env`, `AccountConfig`, `require_live_credentials()` | Credentials never hardcoded |
| Trend collector | `app/trend_collector/collector.py` | `get_collector()` factory; `MOCK_DEFAULT` / `RANDOMISED` modes | V1 source is bundled mock data; V2 adds new classes here |
| Content generator | `app/content_generator/generator.py` | Template-based caption + PIL meme image | Category palettes so output varies by topic |
| Scheduler | `app/scheduler/scheduler.py` | APScheduler cron at `GENERATION_TIMES`; queues content | **Never imports Publisher** — cannot publish by construction |
| Storage | `app/storage/drive_uploader.py` | Validate locally → upload to Drive | Failures raise for retry; local files never invalidated |
| Publisher | `app/publisher/publisher.py` | `publish_now()` — only path to a real post | Called from `/post-now` route only |
| Graph API client | `app/publisher/graph_api.py` | `publish_image()`, `get_insights()` | HTTPS-only, token from .env, no browser automation |
| Web UI | `app/web/server.py` + `preview.html` | Preview card, Regenerate, Post Now | UI auto-generates a queue item if empty (testing convenience) |
| Composition root | `app/main.py` | Wires concrete classes to interfaces | The only place concrete classes meet |

## Data Flow

1. **Scheduler fires** (09:00 / 19:00 IST by default).
2. **Collector** returns candidate topics, best-first by score.
3. **Generator** builds a `GeneratedContent` locally (image + caption + hashtags).
4. **Storage validates** locally — this step never depends on any network service.
5. **Storage uploads** to Google Drive (mock: local log; live: service account).
6. Content is **queued** and shown in the Flask UI for human review.
7. **Human clicks "Post Now"** → publisher reads the `public_url` from Drive and
   performs the two-step Graph API publish (`media` → `media_publish`).
8. Post ID returned; analytics can later fetch insights via `get_insights()`.

## Environment Modes

| Mode | Env | Behaviour |
|---|---|---|
| Development | `MOCK_MODE=true` (default) | No Drive upload, no Instagram post; everything logged locally |
| Live | `MOCK_MODE=false` + IG credentials + service account | Real Drive uploads + real publishes via `/post-now` |

## Safety Guarantees (CTO-reviewed)

1. **Human-in-the-loop publishing** — the scheduler cannot reach the publisher.
2. **Local-first storage** — Drive being down never blocks generation or preview.
3. **No secrets in code** — everything in `.env` and the service-account JSON; `.gitignore` excludes them.
4. **Idempotent Drive folders** — re-running never duplicates category folders.
5. **Upload failures raise** — scheduler logs and retries; half-uploads are impossible.
6. **Anyone-with-link reader** is set only on uploaded images, so the Graph API
   can fetch the image URL (required because Graph API accepts public HTTPS URLs only).

## V2 Backlog (for CTO review)

The interfaces already exist for: `AnalyticsInterface`, pluggable collectors
(Reddit/Twitter/RSS), LLM-based caption generation (drop-in replacement for
`TemplateContentGenerator`), and duplicate detection in the collector. Each
lands as a new class implementing an existing interface — no module rewrites.
