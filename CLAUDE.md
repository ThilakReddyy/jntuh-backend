# CLAUDE.md

Repository guidance for AI coding assistants and maintainers. Read `architecture.md` before changing result retrieval, queueing, persistence, or cache behavior.

## Product priority

Student results are the primary feature. Preserve the cache-first read path and asynchronous scrape behavior before optimizing supporting features such as jobs, content, chatbot, or grace-marks proof review.

## Stack and processes

- FastAPI routes in `api/routes.py`, with orchestration in `service/`.
- Prisma Python client with PostgreSQL as the source of truth.
- Redis for derived responses, upstream URL state, rate limits, locks, and class-processing suppression.
- RabbitMQ for per-student and class result scrape work.
- `main.py` runs the API plus notification/job schedulers.
- `main2.py` runs the RabbitMQ result worker.
- The `Dockerfile` starts both Python processes in one container; they can be run separately during development.

See `architecture.md` for the component model and end-to-end flows.

## Local setup and commands

Create `.env` from `.env.example` and replace all placeholder credentials before importing application modules. `config/settings.py` exits the process during import when a required variable is absent.

```bash
# Python environment
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt

# Infrastructure only; the committed app service is commented out
docker-compose up -d

# Prisma client/schema
prisma generate
prisma db push

# Run these in separate terminals
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
python main2.py

# Verification
python -m pytest -q
pyright

# Load test after the API is running
locust -f tests/locustfile.py --host http://localhost:8000
```

The repository has pytest coverage for the API guard, OpenAPI, chatbot, CMM generation/classification gate, jobs, subscriptions, Android/iOS notifications, class consumption, and RabbitMQ publishing. It also has Locust load tests. `pyrightconfig.json` roots type checking at the repository root.

At the current revision, `tests/test_rabbitmq_publisher.py` expects a class queue with four messages to accept another item, while `CLASS_RESULTS_QUEUE_MAX_MESSAGES` is 3 and the publisher rejects at that threshold. Keep the test and production constant aligned when changing this area.

## Environment configuration

Startup-required variables are defined by `required_env_vars` in `config/settings.py`:

- `RABBITMQ_URL`, `DATABASE_URL`, `QUEUE_NAME`, `REDIS_URL`
- `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`
- `GRACE_MARKS_ADMIN_KEY`

Important optional groups:

- API/docs: `API_ACCESS_KEY`, `ENVIRONMENT`
- S3-compatible development storage: `S3_ENDPOINT_URL`, `S3_PUBLIC_URL_BASE`
- CMM verification: `GEMINI_API_KEY`, `GEMINI_MODEL`, `CMM_REFERENCE_PATH`
- Chatbot: `CHATBOT_API_KEY`, `CHATBOT_BASE_URL`, `CHATBOT_MODEL`, and bounded timeout/tool/output settings
- Android push: `GOOGLE_APPLICATION_CREDENTIALS`, `FIREBASE_PROJECT_ID`, `FCM_RESULTS_TOPIC`
- iOS push: `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, and either `APNS_PRIVATE_KEY` or `APNS_PRIVATE_KEY_PATH`
- Class work: `CLASS_RESULTS_QUEUE_NAME`
- Job sources: `JOB_ATS_BOARDS_JSON`

Never commit `.env`, service-account JSON, APNs `.p8` files, private keys, access tokens, or real production identifiers. The current Compose file does not define MinIO. To use local object storage, run an S3-compatible service separately and point `S3_ENDPOINT_URL` at it; `utils/s3.py` creates the configured bucket lazily for custom endpoints.

## Result read path

All student result views derive from normalized attempts in PostgreSQL:

1. Look up the view-specific Redis key.
2. On cache miss, load the student and marks from PostgreSQL.
3. If stored data exists, project it into the requested view and cache it.
4. Only the consolidated academic-result DB-hit path currently schedules a background freshness scrape. Do not describe or implement every stored read as refreshing automatically.
5. If no stored student exists, publish the roll number and return `202 Accepted`.
6. The worker scrapes JNTUH, upserts normalized records, invalidates the main student keys, and notifies subscribers when new marks were inserted.

Primary keys and TTLs:

- `<rollNo>Results`, `<rollNo>ALL`, `<rollNo>Backlogs`, and `<rollNo>RequiredCredits`: 1,200 seconds.
- `<rollNo1><rollNo2>ResultContrast`: 1,200 seconds, but not deleted by `invalidate_all_cache()`.
- `<classPrefix>Results+<type>`: 600 seconds, also outside per-student invalidation.

When adding a result cache, update invalidation deliberately or document why TTL-only expiry is acceptable.

## Scraping and grading invariants

- `scrapers/serverChecker.py` probes the canonical JNTUH host and IP fallback. Redis key `url` stores the selected URL; `.` means neither is available.
- `ResultScraper` selects payloads from the roll-number pattern and concurrently requests relevant exam codes.
- `mark` uniqueness includes student, semester, exam, subject, RCRV, and grace flags. Preserve regular, supplementary, RCRV, and grace attempts as distinct records.
- Consolidated views choose the best attempt in `database/models.py`.
- GPA calculation must use `utils.helpers.isbpharmacyr22()` everywhere the B.Pharm R22 table matters.
- Use `utils.helpers.validateRollNo` for public roll-number inputs instead of reimplementing validation.

## Queue behavior

- Normal queue: `QUEUE_NAME`; the publisher returns 429 only when the current count is greater than `RABBITMQ_MAX_MESSAGES` (4,000).
- Class queue: `CLASS_RESULTS_QUEUE_NAME`, default `classresults`; the publisher refuses at `CLASS_RESULTS_QUEUE_MAX_MESSAGES` (3).
- Class reads refuse work when the normal queue exceeds `RABBITMQ_CLASS_MAX_MESSAGES` (500) and publish a refresh only while it is below `RABBITMQ_CLASS_PUBLISH_MAX_MESSAGES` (50).
- Worker prefetch is 2 for normal messages and 1 for class batches.
- Class batches stop after 20 consecutive empty roll numbers and set paired Redis suppression keys for 24 hours.
- `RABBITMQ_ROLL_NUMBERS` is currently removed by the consumer but is not added by `messaging/publisher.py`; do not claim active Redis-set de-duplication without implementing both sides.

Class cohort pairing follows JNTUH admission-year/type rules implemented in both `messaging.consumer.get_class_prefixes()` and `service/getClassResults.py`. Do not simplify it to a literal `5↔A` character swap.

## Notifications and schedules

- The API runs `refresh_notifications_periodically()` immediately and every 60 seconds.
- Notification refresh caches the raw scrape for 30 minutes, upserts `examcodes`, and broadcasts only newly inserted releases through Telegram, FCM, and APNs.
- Public notification response caches expire after five minutes.
- The API runs the job scrape immediately and every 24 hours under a Redis lock.
- Student scrape inserts send legacy Web Push plus Android/iOS result-ready notifications.

Provider failures should not roll back already-persisted results or notification metadata.

## API, MCP, and security

- `ApiKeyHeaderMiddleware` protects most HTTP routes with `X-Api-Key`. When `API_ACCESS_KEY` is unset, any non-empty value passes.
- Exact/prefix mobile User-Agents bypass the header guard. Treat this as a compatibility filter, not strong authentication.
- `/mcp`, `/metrics`, docs, `/`, `/connect`, and preflight requests are exempt. `/api/health` is not exempt.
- Default rate limit is 30/minute by originating IP with Redis storage and an in-memory fail-open fallback. `/mcp` is exempt; sensitive routes define tighter limits.
- MCP exposes only the GET operations in `config/mcp.py`. Keep mutation/admin operations out of the allowlist.
- The chatbot may call only that same read-only MCP tool set.
- `ENVIRONMENT=production` disables public Swagger, ReDoc, and OpenAPI routes but not internal schema generation for MCP.

See `SECURITY.md` before changing authentication, admin routes, uploads, secrets, or dependency versions.

## Grace marks and storage

- Eligibility requires B.Tech/B.Pharm, stored 4-2 marks, and remaining backlogs.
- Proof upload repeats eligibility checks, enforces PDF/PNG/JPEG and 5 MB, and fails closed when Gemini verification is unavailable.
- Upload only a confirmed CMM to S3-compatible storage, then persist its metadata.
- Admin proof review and grace-mark writes require `GRACE_MARKS_ADMIN_KEY`.
- Grace-mark writes invalidate the primary per-student result keys.
- `/api/getCMM` generates a watermarked sample PDF and is separate from uploaded proof storage.

## Observability

- FastAPI metrics: `/metrics`.
- Prometheus also scrapes RabbitMQ and Redis/PostgreSQL exporters.
- Component logs go to files/stdout and Loki through `utils/logger.py`.
- The Loki endpoint is currently hard-coded, so account for host-versus-container networking before changing deployment topology.

## Deployment caveat

Pushes to `main` trigger `.github/workflows/deploy.yml`, which expects a Compose service named `app`. That service is commented out in the committed `docker-compose.yml`. Production therefore needs an environment-specific Compose override or an enabled service before the workflow commands can succeed. Do not document the committed Compose file as a complete production deployment.

See `DEPLOYMENT.md` for the deployment contract and `RUNBOOK.md` for incident procedures.

## Change checklist

- Keep route operation IDs stable when MCP clients depend on them.
- Keep cache keys, TTLs, and invalidation synchronized.
- Update Prisma generation/schema instructions when modifying `prisma/schema.prisma`.
- Add or update tests for queue thresholds, response projections, auth exemptions, and notification contracts.
- Update `architecture.md`, `RUNBOOK.md`, and deployment/security docs when behavior changes.
- Preserve unrelated local changes in a dirty worktree.
