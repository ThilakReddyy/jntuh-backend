# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

FastAPI + Prisma (Python client) + PostgreSQL + Redis + RabbitMQ. The deployed app sits behind Cloudflare and a reverse proxy on EC2 (see `.github/workflows/deploy.yml`); container build is `Dockerfile`, dev infra is `docker-compose.yml`.

## Common commands

```bash
# Bring up Postgres / Redis / RabbitMQ / Prometheus / Grafana / Loki (the `app` service is commented out — run the API on the host)
docker-compose up -d

# Generate the Prisma client and apply schema. Run after editing prisma/schema.prisma or on first setup.
prisma generate
prisma db push

# Run the API (host)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run the RabbitMQ consumer (must run alongside the API for any scrape to complete)
python main2.py

# Stress / load test
locust -f tests/locustfile.py --host http://localhost:8000
```

There is no unit-test suite or linter wired up. `pyrightconfig.json` enables Pyright type checks rooted at `./`. The `tests/` directory contains only Locust load tests.

Required env vars (validated at startup in `config/settings.py` — the process exits if any are missing): `RABBITMQ_URL`, `DATABASE_URL`, `QUEUE_NAME`, `REDIS_URL`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`. See `.env.example` for the local format.

## Architecture

The system has two long-running Python processes that share Postgres / Redis / RabbitMQ:

1. **API** (`main.py`) — FastAPI app. Routes live in `api/routes.py` and delegate to `service/*`. Lifespan hook opens RabbitMQ + Prisma + Redis.
2. **Consumer** (`main2.py` → `messaging/consumer.py`) — pulls roll numbers off `QUEUE_NAME`, runs `scrapers/resultScraper.py` against the JNTUH results servers, persists via `database/operations.py`, and invalidates the student's Redis keys via `utils/caching.py:invalidate_all_cache`.

### Read path (read-through cache → DB → queued scrape)

For a result-style endpoint (e.g. `service/getResultsService.py:fetch_results`):

1. Check Redis (`<rollNo>Results`, `<rollNo>ALL`, `<rollNo>Backlogs`, `<rollNo>RequiredCredits`) — return immediately on hit, with a live `serverStatus` flag derived from `scrapers/serverChecker.py:check_valid_url_in_redis`.
2. On miss, read from Postgres via Prisma (`database/operations.py:get_details`). If found, cache for `EXPIRY_TIME` (1200 s) and **also** publish a refresh message to RabbitMQ.
3. On full miss, return `202 Accepted` from `messaging/publisher.py:publish_message` and let the consumer scrape asynchronously.

Implication: every successful read also schedules a re-scrape. When changing this flow, keep the cache key naming consistent — `utils/caching.py:invalidate_all_cache` knows them by hard-coded suffix and must be updated in lockstep.

### Scraper

`scrapers/resultScraper.py:ResultScraper` fans out concurrent `aiohttp` requests across exam codes loaded from `data/examCodes.py`. Per-degree URL payloads are in `_load_payloads`. Two grade-to-GPA tables exist — the regular one and a separate B.Pharm R22 table; selection is via `utils/helpers.py:isbpharmacyr22` (rule: 6th char `R` and grad-year ≥ 23, or year `22` with non-`5` 5th char). Match this discriminator everywhere a GPA is computed.

`scrapers/serverChecker.py` probes two upstream JNTUH hosts (`results.jntuh.ac.in` and the IP fallback `202.63.105.184`) and caches the working URL in Redis under the key `url`. The publisher refuses to enqueue if this resolves to `.` (sentinel for "both upstreams down") and returns `424 Failed Dependency`.

### Messaging back-pressure

`messaging/publisher.py:publish_message` checks `queue.declaration_result.message_count` against `RABBITMQ_MAX_MESSAGES` (4000) and returns `429` when the queue is saturated. Class-level requests use `RABBITMQ_CLASS_MAX_MESSAGES` (200). Each enqueue also adds the roll number to a Redis set `rabbitmq_roll_numbers` for de-dup; the consumer SREMs it on success.

### Notifications path

`scrapers/resultNotificationScraper.py` (driven on demand by enqueueing the sentinel `NOTIFICATIONS_REDIS_KEY = "notificationsi"` to the same queue) refreshes JNTUH result notifications, fans out push notifications via `subscriptions/send_notification.py` and Telegram via `utils/helpers.py:send_telegram_notification`. Notification API responses are cached for 5 min (`FIVE_MINUTE_EXPIRY`) per filter combination.

### Data shape

Prisma schema (`prisma/schema.prisma`):
- `student` 1—∞ `mark` ∞—1 `subject`. Uniqueness on `(studentId, semesterCode, examCode, subjectId, rcrv, graceMarks)` — the same subject can appear under regular, RCRV (revaluation), and Grace variants. Models in `database/models.py` collapse these into a "best grade per subject" view (`studentResultsModel`) using `utils/helpers.py:isGreat`.
- `examcodes` is the catalog of result-release notifications scraped from JNTUH.
- `AnonPushSubscription` stores anonymous web-push endpoints by `anonId` UUID.
- `Job` / `JobLocation` / `JobOnLocation` for the jobs board scraped by `scrapers/jobScraper.py`.

### MCP

`main.py` mounts an MCP server via `FastApiMCP` at `/mcp` (`mount_http()`), exposing only the read-only `get_*` / `check_*` operation IDs explicitly listed in `include_operations`. Destructive endpoints (`hardRefresh`, `save-subscription`, etc.) are intentionally not exposed. `/connect` serves `static/mcp_setup.html` as a connector setup guide.

### Observability

- Prometheus instrumentation auto-mounted at `/metrics` via `prometheus_fastapi_instrumentator`.
- Loki logging via a single shared `LokiQueueHandler` pushing to `http://localhost:3100`. Per-component file loggers (`rabbitmq.log`, `database.log`, `redis.log`, `scraper.log`, `telegram.log`, `app.log`) are configured in `utils/logger.py` and re-used across modules — import the right named logger instead of creating a new one.
- Grafana dashboards reach Postgres / Redis via `postgres_exporter` and `redis_exporter` sidecars defined in `docker-compose.yml`.

### Rate limiting

`config/rateLimiter.py` defines a shared `slowapi` `Limiter` keyed by the real client IP (resolved from `CF-Connecting-IP` → `X-Forwarded-For` → socket peer, in that order — required because the app runs behind Cloudflare). Default limit is `30/minute`, storage is Redis with in-memory fallback, and it fails open on Redis errors. Wired into `main.py` via `ExemptingSlowAPIMiddleware` (also defined in `rateLimiter.py`), which short-circuits paths under `EXEMPT_PATH_PREFIXES` — currently `/mcp`, since slowapi 0.1.10 does not actually auto-skip mounted sub-apps despite the docs. SlowAPI is added before CORS so CORS sits outermost and 429 responses still carry `Access-Control-Allow-Origin`.

## Conventions worth knowing

- Roll numbers are validated by `utils/helpers.py:validateRollNo` (10 chars, alphanumeric, upper-cased). Always go through this dependency rather than hand-validating.
- Class-results endpoints derive the section from `roll_number[:8]` and look up the paired day/evening cohort by swapping the 5th char with the rule `5↔A`.
- B.Tech credit thresholds for `getCreditsChecker` are hard-coded in `utils/helpers.py:get_credit_regulation_details` keyed on regulation (`R18` / `R22`) and entry type (`Regular` / `Lateral`, decided by `roll_number[4]`). Other degrees return a failure response.
- The frontend origins allowed in CORS are hard-coded in `main.py` (`jntuhresults.dhethi.com`, `jntuhconnect.dhethi.com`, `dhethi.com`, `localhost:3000`). Add new origins there, not via env.

## Deploy

`main` → GitHub Actions (`.github/workflows/deploy.yml`) → SSH to EC2 → `git reset --hard origin/main` → `docker-compose build app && docker-compose up -d --no-deps app` → `docker system prune -af`. The `app` service is commented in the committed compose file but is expected to exist in the deployed copy.
