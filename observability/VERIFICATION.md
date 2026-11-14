# Local verification — 2026-11-14

Tested in an isolated `jntuh-observability-test` Compose project on Docker Desktop
27.4 / Linux arm64. No production deployment or production data-store change was
performed. The production Linux configuration was rendered and validated; EC2
runtime behavior still requires deployment verification on that host.

- Application regression suite: **99 passed**, 4 existing warnings.
- Prometheus config validated with `promtool`: **13 scrape jobs, 14 alert rules**.
- Alert rule tests: target failure/recovery, dependency readiness, disconnected
  worker, and host memory pressure all passed.
- All **13 live scrape jobs** healthy, including API, worker, host and containers.
- All **7 dashboards** and **3 data sources** provisioned in Grafana.
- All **74 metric panel expressions** executed successfully through Grafana's
  Prometheus proxy. Unused MCP/error operations and unconfigured CPU throttling
  can have no series; these are not represented as measured zero.
- Loki searches (including All services and parsed warning/error logs) and Tempo
  TraceQL search executed through Grafana successfully.
- Verified the configured log-derived trace regex against an actual trace ID and
  verified Grafana's provisioned trace-to-log query.
- A synthetic HTTP request was found in Prometheus, Loki and Tempo using its
  returned request/trace IDs. Application metrics expose OpenMetrics exemplars.
- A student request trace contained **both `jntuh-api` and `jntuh-worker`**, with
  **340 spans** across HTTP, cache, publishing, consumption, scraping and database
  operations. Full response bodies/student records were not printed or committed.
- Stopping RabbitMQ changed the worker connection gauge to **0**; restarting it
  allowed the robust connection to recover. Worker rules/dashboard queries are
  scoped to the worker scrape job, excluding API-process placeholder gauges.
- Stopping Redis changed `/health/ready` to **503** with only Redis marked down;
  Prometheus's readiness probe became **0**. Restoring Redis recovered HTTP **200**.
- Docker images built successfully. A pre-existing Prisma/nodeenv build failure
  was fixed by pinning the Node runtime used to generate Prisma.

## Supplied roll-number flows

Each first request reached the queue with HTTP 202 and a trace ID. Subsequent reads:

| Roll number | Observed response after worker processing |
| --- | --- |
| 198R1A05C4 | 200 |
| 21HA1R0002 | 200 |
| 24011P0164 | 202 — no stored result obtained in the test window |
| 18E51A0473 | 200 |
| 18E51A0479 | 200 |

A queued or empty result does not establish that a student has no record. Actual
university availability and record coverage remain outside this stack's control.
Provider notifications were not verified with real credentials. Periodic refresh
schedulers were disabled for the isolated smoke run.

The browser integration could not initialize in this session. Provisioning,
queries, trace retrieval and correlation configuration were checked through
Grafana/backend APIs; a visual screenshot review was not performed.

Re-run `scripts/observability_smoke.py`, `pytest`, and `promtool test rules` after
updates; see [the operating guide](../OBSERVABILITY.md).

## Deployment compatibility follow-up

The EC2 deployment reported `unknown flag: --quiet` from the top-level Docker CLI
because a supported `docker compose` plugin was not available. Deployment now runs
`scripts/ensure_compose.py` before configuration validation, build or service changes.

- 25 targeted preflight/observability tests passed, covering version detection,
  installation selection, checksum protection and fail-fast deployment behavior.
- In a disposable Linux x86_64 Docker CLI 27 container with Compose removed, the
  preflight installed Compose v2.40.3 and reused it on the second invocation.
  `docker compose config --quiet` accepted this repository's configuration, and
  `up --help` confirmed support for `--wait-timeout`.
- Official release assets were downloaded from GitHub on the host. The Linux
  container used identical mounted assets for the download step because local
  Docker DNS could not resolve GitHub; checksum verification, binary execution
  and Docker plugin discovery ran inside the Linux container.
- No production host changes or workflow rerun were performed during this fix.
