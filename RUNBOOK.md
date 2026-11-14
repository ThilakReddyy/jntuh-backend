# Operations Runbook

This runbook covers the result-serving path and its supporting infrastructure. PostgreSQL is authoritative; Redis entries are rebuildable; RabbitMQ decouples API requests from JNTUH scraping.

## Quick triage

Identify the affected scope first:

1. Is the API reachable?
2. Are cached results failing, or only new/uncached roll numbers?
3. Are PostgreSQL, Redis, and RabbitMQ reachable?
4. Do both result queues have consumers?
5. Are the JNTUH upstreams reachable?
6. Is the issue limited to notifications, CMM proofs, jobs, or chatbot?

Basic checks from the deployment host:

```bash
docker-compose ps
docker-compose logs --tail=200 app
docker-compose exec db pg_isready -U postgres
docker-compose exec redis redis-cli ping
docker-compose exec rabbitmq rabbitmq-diagnostics ping
docker-compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

Public checks:

```bash
curl -i -H "X-Api-Key: $JNTUH_API_KEY" https://jntuhresults.dhethi.com/api/health
curl -fsS https://jntuhresults.dhethi.com/metrics > /dev/null
```

`/api/health` is protected by the API header guard. `/metrics` is exempt.

## Logs and metrics

Application/component files:

- `app.log`
- `rabbitmq.log`
- `database.log`
- `redis.log`
- `scraper.log`
- `telegram.log`

Logs also flow to Loki when its configured endpoint is reachable. Use Prometheus/Grafana to correlate API latency/status, RabbitMQ depth, Redis health, and PostgreSQL health. A local/container networking mismatch in `utils/logger.py` can prevent Loki delivery without stopping application requests.

## Result request returns 202 indefinitely

`202 Accepted` is normal for a cache-and-database miss. It becomes an incident when repeated retries never produce stored data.

Check:

1. The `main2.py` worker is running.
2. `QUEUE_NAME` is identical in the API and worker environments.
3. The normal queue has at least one consumer.
4. RabbitMQ messages are being acknowledged rather than accumulating.
5. The JNTUH upstream check selects a usable URL.
6. Scraper logs show the roll number and a successful database save.
7. Prisma/PostgreSQL errors are absent.

Inspect the cached upstream URL:

```bash
docker-compose exec redis redis-cli GET url
```

`.` means neither configured JNTUH endpoint was usable when checked. The publisher returns 424 in that state. Do not repeatedly enqueue or purge queues to hide an upstream outage; allow requests to retry when the upstream recovers.

After confirming infrastructure health, restart the application service if the worker process died:

```bash
docker-compose restart app
```

Because the current image couples API and worker, this restarts both.

## Cached result is stale

Normal result caches expire after 1,200 seconds. A successful student scrape and grace-mark write delete:

- `<rollNo>Results`
- `<rollNo>ALL`
- `<rollNo>Backlogs`
- `<rollNo>RequiredCredits`

Result-contrast and class-result caches are not deleted by the per-student invalidation helper. They expire by TTL.

For a single affected student, prefer the `/api/hardRefresh` route so the normal validation, invalidation, upstream, and queue rules apply. If manual Redis deletion is necessary, delete only the exact known keys; never flush the Redis database during routine recovery because it also holds rate-limit and coordination state.

## JNTUH upstream outage

Symptoms:

- Result misses return 424.
- Redis `url` is `.`.
- `scraper.log` shows both upstream probes failing.

Actions:

1. Confirm general outbound network/DNS health from the application host.
2. Test only the configured upstream endpoints with low-impact requests.
3. Continue serving PostgreSQL/Redis-backed results.
4. Avoid increasing concurrency or retry frequency against the unavailable third party.
5. Monitor recovery; subsequent checks can replace the sentinel with a working URL.

## RabbitMQ queue saturation

Normal publishing returns 429 when the current queue count is greater than 4,000. Class reads return 423 when normal queue depth is greater than 500. Class refresh publication is allowed only below 50 normal messages, and the dedicated class queue limit is 3.

Actions:

1. Check queue depth, unacknowledged messages, and consumers.
2. Confirm the worker is healthy and connected to PostgreSQL/Redis.
3. Check JNTUH availability; worker throughput depends on it.
4. Restore consumers or upstream access before changing thresholds.
5. Let backpressure protect the upstream and database.

Do not purge a queue without identifying exactly which work will be lost and obtaining explicit operational approval.

## Class results do not refresh

Class processing uses `CLASS_RESULTS_QUEUE_NAME` and one consumer prefetch. It stops after 20 consecutive empty roll numbers. A successfully processed paired cohort is suppressed for 24 hours using keys of the form:

```text
class_results_processed:<eight-character-prefix>
```

Check the dedicated queue, consumer count, normal queue thresholds, and both paired suppression keys. Remove a suppression key only when a deliberate re-run is required and the class queue/upstream are healthy.

## Redis unavailable

Expected impact:

- More PostgreSQL reads and slower response projection.
- No shared derived caches or upstream URL cache.
- Rate limiting falls back to in-memory, fail-open behavior per process.
- Job scheduler locking and class suppression are unavailable.

Actions:

1. Check Redis container/process, memory, and connectivity.
2. Verify `REDIS_URL` from both API and worker environments without printing credentials.
3. Restore Redis and watch database load as caches warm.
4. Do not treat cache loss as loss of authoritative student marks.

## PostgreSQL unavailable

Expected impact:

- Cache hits may continue temporarily.
- Cache misses, scraper persistence, jobs, content, subscriptions, and proof metadata fail.

Actions:

1. Stop making schema changes.
2. Check host storage, connections, locks, and database logs.
3. Restore PostgreSQL from the normal service or reviewed backup procedure.
4. Verify Prisma connectivity from API and worker.
5. Confirm a known student read and controlled result persistence after recovery.

Never delete the PostgreSQL volume as a restart strategy.

## Result notifications missing

There are two paths:

- New result-release metadata: the API's 60-second scheduler scrapes notifications, writes `examcodes`, then sends Telegram/FCM/APNs broadcasts for newly inserted releases.
- Student result-ready messages: the worker sends legacy Web Push and Android/iOS notifications after inserting new marks.

Check scheduler logs, provider credentials, subscription/device rows, provider responses, and whether new database records were actually inserted. Provider outages should not undo completed result persistence.

When multiple API replicas run, each starts a notification scheduler; investigate duplicate scheduler activity separately from provider retry behavior.

## Grace-marks proof upload fails

Map the response first:

- 400/413: invalid type, empty file, or file larger than 5 MB.
- 422: classifier returned `not_cmm` or `uncertain`.
- 503: Gemini configuration/provider/reference document is unavailable.
- 502: object storage upload failed.
- 500 after upload: object was stored but proof metadata could not be recorded.

Check `GEMINI_API_KEY`, model/reference availability, S3 credentials/bucket/endpoint, and PostgreSQL. Do not bypass classification or make the bucket public as an incident workaround. A metadata failure after upload may leave an orphaned object; record its exact key and reconcile it deliberately.

## Jobs are stale or empty

The jobs scheduler runs immediately at API startup and every 24 hours under Redis lock `jobs:daily-refresh-lock`. It preserves existing records when every source returns no accepted jobs and marks jobs inactive after 45 days unseen.

Check the scheduler log, Redis lock ownership/TTL, outbound source availability, parser errors, and PostgreSQL writes. Do not deactivate all existing jobs merely because one scrape returned no data.

## Chatbot unavailable

- 503: provider configuration is incomplete or invalid.
- 504: provider timed out.
- 502: provider/tool response failed.

Verify `CHATBOT_API_KEY`, `CHATBOT_BASE_URL`, and `CHATBOT_MODEL` without logging values. Confirm MCP read operations work independently. Keep tool allowlists read-only during recovery.

## Monitoring stack failure

Prometheus scrapes FastAPI, RabbitMQ, Redis Exporter, and PostgreSQL Exporter. Grafana depends on the configured data sources; Loki stores application logs.

An observability failure is not necessarily an API failure. Check each target independently, restore monitoring, and use local/container logs while telemetry is unavailable. Restrict monitoring ports from public access.

## Recovery verification

After any incident:

1. API health succeeds with the required header.
2. A known cached and known database-backed result both return correctly.
3. A controlled missing result is queued and consumed.
4. Queue depth trends down and consumers remain active.
5. PostgreSQL writes and Redis cache repopulation succeed.
6. Error rates and latency return to baseline.
7. Notification/provider failures no longer repeat.
8. Document the timeline, cause, actions, lost work, and follow-up changes.

For deployment rollback and environment requirements, see `DEPLOYMENT.md`. For credential exposure or suspected compromise, follow `SECURITY.md`.
