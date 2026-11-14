# JNTUH observability

The stack adds container metrics through cAdvisor, Docker stdout/stderr collection
through Grafana Alloy, OpenTelemetry traces in Tempo, and seven provisioned Grafana
dashboards. Existing Prometheus, Loki, Redis Exporter, and PostgreSQL Exporter
services are reused. `Dockerfile` and `.github/workflows/deploy.yml` are unchanged.
Existing Compose settings are preserved; new environment entries, mounts, services,
and volumes are additive. No validation jobs, startup checks, or tests are added.

## Start on the deployment host

The existing workflow builds and restarts **only app** with `--no-deps`. It cannot
start the new monitoring services or apply Grafana's provisioning mounts. Once
these files are on the host, apply the monitoring additions once:

```bash
docker-compose up -d --no-deps tempo cadvisor alloy
docker-compose up -d --no-deps grafana
docker-compose restart prometheus
docker-compose exec rabbitmq rabbitmq-plugins enable rabbitmq_prometheus
docker-compose build app
docker-compose up -d --no-deps app
```

This assumes the existing PostgreSQL, Redis, RabbitMQ, Loki, Prometheus, and
exporter services are already running. The RabbitMQ command enables its metrics
plugin in place; the added `enabled_plugins` mount supplies the same plugin list
on subsequent container creation. It does not require recreating the live broker
to turn metrics on. Later app-only deployments continue to use the existing
workflow. Changes to monitoring configuration require applying the relevant
service explicitly again.

For a fresh environment, the existing `docker-compose up -d --build` starts the
whole stack after the application's existing required environment is configured.

cAdvisor's host mounts and `/dev/kmsg` target the Linux EC2 Docker host. They
observe the Docker host/VM rather than macOS processes on Docker Desktop. Alloy
uses the Docker socket to discover Compose containers and read their logs. The
new services and worker metrics endpoint have no published host ports; Grafana
remains available on its existing port 3000 and keeps its existing credentials.

cAdvisor also mounts `/var/run/docker.sock` explicitly. On Docker Desktop,
mounting `/var/run` alone can expose an inaccessible socket symlink: Prometheus
then reports cAdvisor as up, but only the root cgroup is exported and the container
dashboards are empty. Apply a socket-mount change with
`docker compose up -d --no-deps cadvisor`; restarting the existing container does
not apply new mounts.

## Grafana dashboards

Open Grafana, then **Dashboards → JNTUH Observability**. Datasources are provisioned
as **JNTUH Prometheus**, **JNTUH Loki**, and **JNTUH Tempo**, with dedicated UIDs;
existing datasources and dashboards are retained.

| Dashboard | Coverage |
| --- | --- |
| Stack Overview | Scrape health, API rate/errors/latency, queues, backend errors, per-container resources, and stack logs. |
| Containers | Project/service selectors cover every running Compose container, including exporters and monitoring services: CPU, working set/RSS, limit utilization, network RX/TX/errors/drops, filesystem, throttling, uptime, and logs. |
| API and Result Worker | HTTP route/status rates and p50/p95 latency, operation durations/errors/in-flight work, core result cache outcomes, scraping, MCP tools, separate Python process CPU/RSS, container resources, and logs. |
| PostgreSQL | Availability, connections, commits/rollbacks, cache hit ratio, row activity, deadlocks, temporary writes, database container resources, and server logs. |
| Redis | Availability, clients, used/RSS/max memory, cache hit ratio, commands and mean latency, expirations/evictions, keys, connection rejections, network, container resources, and server logs. |
| RabbitMQ | Availability, connections/channels, per-queue depth/consumers, publishes/deliveries/acks/redeliveries, memory/disk watermarks, descriptors, container resources, and broker logs. |
| Logs and Traces | All container logs with literal text search, application warnings/errors, trace-ID filtering, and recent application traces. |

Project/service variables filter container metrics and Docker logs. Application
and infrastructure exporters describe the single configured stack; the project
selector does not turn exporter panels into multi-cluster queries. Missing
metrics remain empty rather than being replaced with misleading zeroes.
CPU 100% means one fully occupied CPU core, so multi-core usage can exceed 100%.
Containers without explicit memory limits can report the host memory limit.
Network panels show traffic and network errors/drops; logs are service stdout and
stderr, not packet captures or PostgreSQL SQL-query logging.

## Logs and traces

Application and component loggers emit JSON to stdout. Alloy labels Docker logs
with `job="docker"`, `compose_project`, `compose_service`, and `container`, and
forwards the original lines to Loki once. Trace IDs and request IDs remain JSON
fields rather than stream labels. Infrastructure logs use their original format.

Application logs use a bounded background queue before formatting/output, so
stdout and optional disk writes do not run on the request thread. Correlation
IDs are captured before queuing. `LOG_QUEUE_SIZE` defaults to 4,096 records;
overflow drops records instead of blocking requests and increments
`application_log_records_dropped_total`. The queue drains on normal process exit.

Docker stdout and Alloy/Loki are the default outputs. Set `LOG_FILE_ENABLED=true`
to additionally write `app-<pid>.log` and component files such as
`database-<pid>.log`: 10 MiB each with three backups, also in the background.
API and worker use separate files to avoid competing rotations. Old PID files
can be removed after the process exits. `LOG_DIRECTORY` changes the local
directory; `LOG_LEVEL` defaults to `INFO`.

API responses include `X-Request-Id`, and `X-Trace-Id` when tracing is configured.
The outer request span observes middleware rejections, failures, and complete
streaming responses. Access logs use route templates and omit query strings,
client IPs, headers, and bodies. Existing business log messages are preserved;
they may still contain roll numbers, so log access remains operator-only.

Queue publication injects W3C `traceparent`/`tracestate` headers without changing
the message body. Both consumer queues extract them; messages created before
instrumentation still work. Traces cover HTTP → queue publication → worker →
Redis reads for the four core result views and cache invalidation, database
reads/writes and JNTUH exam fetches, plus class batches, MCP requests,
notification refreshes and job refreshes. Span names and metric labels contain
operation/route names, not student IDs, cache keys, SQL, payloads, or upstream
query strings. Queue thresholds, acknowledgement, cache TTLs and result behavior
are unchanged.

Expand a JSON log in Grafana and select **View trace** beside TraceID. Tempo links
back to Loki through **Logs for this span**. The Logs and Traces dashboard accepts
a response's trace ID to show related API and worker logs. Sampling can leave a
log trace ID without a stored trace.

Trace batches are exported in the background with a queue of 16,384 spans and a
3-second exporter timeout. An unavailable Tempo does not block requests on a
network export; batches can be dropped when the queue fills. Tempo retains traces
for 72 hours in `tempo_data`. Alloy persists collection state in `alloy_data`.

## Optional runtime configuration

| Setting | Default outside Compose |
| --- | --- |
| `OTEL_ENABLED` | `true`; set `false` to disable trace export. |
| `OTEL_FUNCTION_TRACING_ENABLED` | `true`; adds nested application function spans to sampled request/job traces. Set `false` to retain the existing HTTP, queue and operation spans with less trace volume. |
| `OTEL_FUNCTION_TRACING_MODE` | `boundary`; traces route/service/database/storage boundaries. Set `full` temporarily for every decorated helper, including per-subject and parser calls. Restart the app after changing this setting. |
| `OTEL_BSP_MAX_QUEUE_SIZE` / `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` / `OTEL_BSP_SCHEDULE_DELAY` | `16384` spans / `1024` spans / `1000` milliseconds; export buffer and batch cadence sized for function tracing. |
| `OTEL_SERVICE_NAME` | `jntuh-backend`; trace resources append `-api` or `-worker`. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Empty; no remote trace export. Compose supplies `http://tempo:4318/v1/traces`. |
| `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` | Parent-based 10% sampling for new root traces; explicit standard OTel sampler settings take precedence. Parent decisions propagate through RabbitMQ. |
| `LOG_FILE_ENABLED` | `false`; Docker stdout/Alloy/Loki remain active. |
| `LOG_OPERATION_COMPLETIONS` | `false`; disables routine function completion INFO logs. Warnings, errors, request logs and existing business/lifecycle logs remain active. |
| `LOG_QUEUE_SIZE` | `4096` records per process; bounded asynchronous log output. |
| `WORKER_METRICS_ENABLED` | `false`; Compose enables it. |
| `WORKER_METRICS_HOST` / `WORKER_METRICS_PORT` | `0.0.0.0` / `8001`; internal worker `/metrics`. |

The API continues serving its existing `/metrics`. The worker has a separate
Prometheus registry/process endpoint, avoiding multiprocess directory or image
changes. Prometheus additionally scrapes cAdvisor, RabbitMQ per-object queue
metrics, itself, Loki, Tempo and Alloy. RabbitMQ's management and Prometheus
plugins are enabled together by the additive mounted plugin list.

## Function tracing and application logs

`@trace_function` supports synchronous functions, asynchronous functions, methods,
properties, route/dependency handlers, and synchronous generator execution across
`api`, `service`, `database`, `scrapers`, `subscriptions`, `messaging`, `chatbot`,
`utils` and `data`. Existing `@observe` functions retain their operation names and
include code metadata, without an additional duplicate function span. Span names
identify the module and qualified function, for example
`service.getResultsService.fetch_results`. Attributes identify the function,
module and source line; arguments, return values and raw exception messages are
never attached. By default, only application boundaries are wrapped; tiny helpers,
schema validators, per-row/per-grade computations and generator steps remain
ordinary function calls with no tracing wrapper. `OTEL_FUNCTION_TRACING_MODE=full`
enables their decorators when detailed debugging is needed. In that mode,
generators attach tracing context only while executing so a yielded value does
not leave a child span active in the caller.

These spans join an active sampled request or job. Calls during import/startup
do not create separate root traces. Telemetry/logging internals and existing
configuration files are not wrapped. Long-running consumer and scheduler loops
remain process boundaries; individual queue messages and scheduled runs already
have operation spans. The existing sampler controls how many request/job traces
are exported. The function-tracing switch controls the extra per-function spans.

Set `LOG_OPERATION_COMPLETIONS=true` to log routine service/delivery completions
with operation, outcome and duration; this extra INFO volume is off by default.
Caught database, queue, notification, subscription and
chatbot failures log ERROR with the operation and exception type, and mark the
active span as failed. Degraded upstreams, retry attempts, unavailable tools,
queue backpressure and HTTP 4xx responses log WARNING. Successful requests and
key lifecycle transitions log INFO. New failure logs omit exception text,
credentials, device tokens and payloads; no new business validation is added.

When a student's result save inserts zero new marks, its INFO message is
`No new records to insert in <rollNo>`. Shared exam-notification updates have no
student roll number and use `No new exam-code records to insert` instead.

The defaults prioritize result-serving latency. For a short diagnostic session,
set `OTEL_FUNCTION_TRACING_MODE=full` and, if needed,
`OTEL_TRACES_SAMPLER=parentbased_traceidratio` plus
`OTEL_TRACES_SAMPLER_ARG=1.0`; restart the app. Return to boundary mode and a
sample ratio of `0.1` afterward. All-request/per-function tracing can generate
thousands of spans per scrape. Prometheus request/error/operation metrics remain
unsampled regardless of the tracing sampler.

## Configuration references

- [cAdvisor Docker deployment](https://github.com/google/cadvisor/blob/v0.60.6/README.md)
- [Alloy Docker log collection](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/)
- [Tempo datasource provisioning](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/provision/)
- [OpenTelemetry Python exporters](https://opentelemetry.io/docs/languages/python/exporters/)
