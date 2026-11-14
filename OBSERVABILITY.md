# Grafana observability for Docker Compose

Everything is provisioned from this repository. There are no Kubernetes pods or
cluster dependencies. Grafana is the entry point for metrics, logs and traces.

## Dashboards

Open **Dashboards → JNTUH Observability**. All dashboards refresh every 5 seconds;
Prometheus collects samples every 10 seconds. Rate panels use a rolling window
(at least 40 seconds), so they are near real time, not instantaneous measurements.
Use **Explore → Loki → Live** for continuously streaming container logs.

| Dashboard | What it shows |
| --- | --- |
| Overview & Alerts | Target health, API throughput/latency, dependency readiness, queue depth, operation outcomes, pending/firing alerts |
| Host CPU Memory Network & Disk | Host CPU modes, load, available/used memory, swap, NIC receive/transmit/errors/drops, filesystem free space, disk I/O, uptime, file descriptors and TCP connections |
| Docker Containers | Per Compose project/service CPU cores, memory working set/RSS/limits, network, filesystem I/O, CPU throttling, OOM events, uptime and last-seen age |
| API Cache & MCP | Route/status traffic, p95 latency, 4xx/5xx, active requests, result-cache hits/misses/errors, database operations, MCP tool traffic/latency |
| Worker Queues & Scraping | Worker connection and event-loop heartbeat, queue backlog/unacknowledged messages/consumers, publish rate, scrape/worker/upstream outcomes and timings |
| PostgreSQL & Redis | Availability, connections, database size, commits/rollbacks/deadlocks/cache ratio, Redis memory/clients/commands/evictions/cache activity |
| Logs & Traces | Filterable container logs, warnings/errors, recent distributed traces, links from log trace IDs to Tempo |

The host exporter uses the host network/PID namespaces so network panels reflect
host interfaces, rather than the exporter's own network namespace. Container CPU
is measured in cores (1 = one fully used CPU). Memory working set differs from RSS
and from Docker's presentation of cached memory. Unlimited containers show host
capacity as their memory limit. Uptime resets on restart/recreation; it is not a
persistent lifetime restart counter. Kernel/runtime support determines whether
OOM, throttling and filesystem metrics exist. No-data on an unused operation
means no sample has been emitted yet, not necessarily a collector failure.

## Start or deploy

1. Keep the existing Compose project name and PostgreSQL/Grafana/Loki/Prometheus
   volumes. Do not use `down -v`. Take normal database/volume backups before the
   first infrastructure upgrade. The old RabbitMQ container had no persistent
   volume: let its existing queues drain before replacing it with this version.
2. Set `GRAFANA_ADMIN_PASSWORD` in the host `.env` to a strong password. Optionally
   set `GRAFANA_ADMIN_USER` (default `admin`). These bootstrap settings only apply
   to an empty Grafana database; an existing Grafana volume retains its login.
3. The deployment script checks for Docker Compose v2.24.4 or newer (`docker compose`).
   If the plugin is missing or too old on Linux, it installs pinned Compose v2.40.3
   from Docker's official release into the deployment user's
   `${DOCKER_CONFIG:-~/.docker}/cli-plugins` directory after SHA-256 verification.
   Docker Engine and Python 3 must already be installed; no sudo or daemon restart
   is needed for the plugin. The GitHub deployment workflow runs
   `bash scripts/deploy.sh`, builds a version-tagged application
   image, starts the entire stack, checks service health, and verifies telemetry.
   A dedicated one-shot `migrate` service runs `prisma db push --skip-generate`
   because this repository has no migration history. It does not accept data loss.
4. On EC2, run `bash scripts/deploy.sh`. The API and worker run as separate services.
   API/worker failures restart independently. Health checks report dependency or
   event-loop failures; Docker alone does not restart an otherwise running process
   merely because it becomes unhealthy.
5. Grafana listens on `127.0.0.1:3000` by default. From your computer:

   ```bash
   ssh -L 3000:127.0.0.1:3000 <user>@<ec2-host>
   ```

   Open http://localhost:3000. Alternatively place Grafana behind your authenticated
   HTTPS reverse proxy. `GRAFANA_BIND_ADDRESS` and `GRAFANA_PORT` control the bind.

For Docker Desktop, use:

```bash
docker compose -f docker-compose.yml -f observability/compose.desktop.yml up -d --build --wait
```

The override removes shared mount propagation unsupported by Docker Desktop and
points the host scrape at the VM bridge gateway. If you changed Docker's default
bridge subnet, set `DOCKER_VM_GATEWAY` to the gateway reported by
`docker network inspect bridge`.
Host metrics then describe the Docker Linux VM, not macOS. Ports can be changed
with `APP_PORT`, `POSTGRES_PORT`, `REDIS_PORT`, `RABBITMQ_PORT`,
`RABBITMQ_MANAGEMENT_PORT` and `GRAFANA_PORT`.

The app retains its existing required environment variables from
`config/settings.py`. `BACKGROUND_REFRESH_ENABLED=false` disables periodic
notification/job refresh only for isolated testing; keep it enabled in production.

## Trace a slow or failing request

Responses include `X-Request-ID` and, when tracing is configured, `X-Trace-ID`.
A bounded incoming request ID is accepted; otherwise one is generated. HTTP
requests produce route-level metrics, including authentication/rate-limit errors.
Health and metrics scrapes are excluded from request telemetry and rate limiting.

1. Find the route/status spike in **API Cache & MCP**.
2. Use **Logs & Traces**, or Explore Loki, to search a request ID:
   `{service="app"} | json | request_id="<id>"`.
3. Expand a log's **TraceID → View trace** link. Tempo includes application
   operations and W3C trace context propagated through RabbitMQ to the worker.
4. A trace's logs link searches API and worker logs by trace ID. Prometheus HTTP
   histograms also expose trace exemplars; use the exemplar link to Tempo.

Instrumented operations cover database service calls (not raw SQL), result-cache
reads, queue publishing/consumption, student processing, JNTUH fetches, result
scraping, notification/job schedulers and MCP handlers. This does not capture
arbitrary Python function calls or all third-party SDK internals. Metrics are
unsampled. `OTEL_TRACES_SAMPLER_ARG=1.0` records all traces; lower it for high traffic.
Parent sampling decisions propagate across the queue. Logs can contain an ID for
an unsampled trace, which will not be present in Tempo.

Student identifiers, payloads, API keys and query strings are not metric labels or
span attributes. Structured application logs redact roll numbers, URL credentials
and URL queries in legacy messages. Raw third-party/container logs remain those
components' responsibility. Traces correlate using opaque IDs, not student IDs.

`empty` means a worker/scraper returned no result; it does not prove the student has
no academic record. `unavailable` and `error` distinguish upstream absence and
handled failures. Existing acknowledgment semantics are preserved: a default
queue handler returning no result is acknowledged, not automatically retried.

## Alerts, retention and operational boundaries

Prometheus evaluates 14 rules for target loss, readiness, API error/latency, worker
stalls, backlog/no consumers, CPU/memory/disk pressure, OOM, datastore availability
and operation errors. They appear in **Overview & Alerts** and Grafana's
Prometheus data-source rule view. Thresholds are starting points in
`observability/alerts.yml`; tune them against real traffic.

No email/Slack/PagerDuty contact point is configured. Rules and dashboards work
without one; outbound paging requires choosing a receiver and wiring Alertmanager
or Grafana-managed rules. This single-host stack cannot notify you when the whole
EC2 host is down; use an external uptime check for that failure mode.

Retention: metrics 15 days or 5 GB, logs 7 days, traces 3 days. Docker stdout logs
rotate at 3 × 10 MB per container. Logs/traces have time retention, not a hard disk
quota; monitor filesystem capacity and size storage against traffic. Named volumes
persist monitoring data across releases. Image tags are pinned for reproducibility;
review and upgrade them regularly.

Alloy reads Docker logs and forwards OTLP spans to Tempo; applications write JSON
to stdout and never synchronously push logs to Loki. The Docker socket and cAdvisor
privileged/host mounts are trusted host-level access, even with read-only mounts.
Keep these collectors private. Backend ports are internal; DB/Redis/RabbitMQ
management binds are loopback. Node Exporter uses host port **9100** for accurate
host networking: block public access to it in the EC2 security group/firewall.
Existing database and RabbitMQ credentials were preserved; rotate them separately
with the corresponding application/exporter settings and existing data stores.

`/metrics` and `/health/*` are unauthenticated for internal probes. Your public
reverse proxy should deny these paths. The existing public `/api/health` is only a
liveness response; `/health/ready` actually checks PostgreSQL, Redis and RabbitMQ.

## Verification and troubleshooting

If deployment reports `unknown flag: --quiet` with top-level `docker` usage,
check `docker compose version`: the CLI plugin is missing or unsupported.
`python3 scripts/ensure_compose.py` performs the same preflight used automatically
by deployment. Legacy `docker-compose` v1 is insufficient for `up --wait` and the
Desktop override. Installation requires HTTPS access to GitHub release assets;
a download/checksum failure stops deployment before any service changes. A
user-local installation is pinned and does not auto-update; review the installer's
`INSTALL_VERSION` when upgrading. Docker documents this installation location in
[its Compose plugin instructions](https://docs.docker.com/compose/install/linux/).

```bash
python3 scripts/observability_smoke.py --skip-results
# Explicitly exercise the five supplied student IDs (can enqueue live scrapes):
python3 scripts/observability_smoke.py
# Syntax and alert rule validation:
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
# Local application regressions:
python -m pytest -q
```

The smoke check verifies all 13 scrape jobs, host and per-container series, worker
readiness, and a real request's metric, Loki log and Tempo trace. It honors
`COMPOSE_FILE` and `COMPOSE_PROJECT_NAME`. A result response of 202 means queued;
424 means the university server is unavailable. Neither proves a completed scrape.

Check `docker compose ps`, `docker compose logs --tail=100 <service>`, and
Prometheus `up` in Grafana Explore. If all container metrics vanish while cAdvisor
is up, verify the Docker socket and host cgroup namespace mounts. If logs vanish,
verify Alloy's `COMPOSE_PROJECT_NAME` matches the deployed project. When changing
mounted collector configuration manually, restart the relevant collector; the
deployment script restarts monitoring services to load config changes. Grafana
reloads dashboard files automatically. Keep one Uvicorn process per API container:
this configuration intentionally uses per-process Prometheus registries.

Recorded local test evidence is in [observability/VERIFICATION.md](observability/VERIFICATION.md).

Configuration references: [Alloy Docker logs](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/),
[Alloy → Tempo](https://grafana.com/docs/tempo/latest/set-up-for-tracing/instrument-send/set-up-collector/grafana-alloy/),
[RabbitMQ Prometheus](https://www.rabbitmq.com/docs/prometheus).
