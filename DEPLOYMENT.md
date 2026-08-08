# Deployment Guide

## Deployment model

Production traffic reaches the FastAPI service through Cloudflare and a reverse proxy on EC2. The application uses PostgreSQL, Redis, RabbitMQ, S3-compatible object storage, notification providers, and external JNTUH result servers.

The application image starts two logical processes:

- Uvicorn serving `main:app` in the foreground.
- `main2.py` consuming result queues in the background.

The API also starts the result-notification and job-refresh schedulers in its lifespan.

For component details and data flows, see `architecture.md`.

## Current repository caveat

The GitHub Actions workflow runs:

```bash
docker-compose build app
docker-compose up -d --no-deps app
```

The `app` service is commented out in the committed `docker-compose.yml`. A clean checkout therefore does not satisfy the deployment workflow by itself. Before relying on automated deployment, do one of the following:

1. Enable and maintain the `app` service in the committed Compose configuration; or
2. Provide a production Compose override and update the workflow to reference it explicitly.

Do not assume a host-only untracked override will survive every provisioning or recovery scenario. Treat the Compose/workflow contract as a release prerequisite.

## GitHub Actions prerequisites

The repository workflow triggers on every push to `main` and requires these GitHub Actions secrets:

| Secret | Purpose |
| --- | --- |
| `EC2_SSH_KEY` | Private key used by the runner to connect to the deployment host. |
| `EC2_USER` | SSH user on the EC2 host. |
| `EC2_HOST` | Hostname or address of the EC2 instance. |

Restrict the SSH key to the deployment host and rotate it if it is exposed. The workflow currently disables strict host-key checking; pinning the host key is recommended before treating the pipeline as hardened.

## Host prerequisites

- Git checkout at `~/jntuh-backend` with an `origin` remote.
- Docker Engine and Docker Compose.
- Network access to the configured PostgreSQL, Redis, RabbitMQ, S3, JNTUH, Gemini, chatbot, Telegram, Firebase, and APNs endpoints as applicable.
- A reverse proxy forwarding the originating client headers expected by rate limiting.
- Cloudflare/proxy configuration that preserves `CF-Connecting-IP` or `X-Forwarded-For`.
- Persistent storage and backups for PostgreSQL and any self-hosted infrastructure.

## Application environment

The container must receive all variables in `config/settings.py:required_env_vars`:

| Group | Variables |
| --- | --- |
| Core data plane | `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `QUEUE_NAME` |
| Web Push | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` |
| Telegram | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` |
| Object storage | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME` |
| Grace-marks administration | `GRACE_MARKS_ADMIN_KEY` |

Production should also set:

- `ENVIRONMENT=production` to disable public interactive docs.
- `API_ACCESS_KEY` to require an exact `X-Api-Key` value outside exemptions.
- `GEMINI_API_KEY` when grace-marks proof upload is enabled; uploads fail closed without it.
- Firebase/APNs credentials for the desired mobile notification channels.
- Chatbot provider settings only when `/api/chatbot` should be available.
- `CLASS_RESULTS_QUEUE_NAME` when the default `classresults` queue name is unsuitable.

Use the platform's secret store or a root-readable environment file outside Git. Never bake credentials into the image or Compose file.

## Database and object storage

The image currently executes `prisma db push` on every container start. Before deploying a schema change:

1. Back up PostgreSQL.
2. Review the Prisma schema diff for destructive operations.
3. Test the change against a representative staging database.
4. Confirm the generated Prisma client is included in the image (`prisma generate` runs during build).

Production S3 buckets should be pre-provisioned with private access and an appropriate lifecycle/retention policy. Automatic bucket creation occurs only when a custom `S3_ENDPOINT_URL` is configured.

## Release flow

The current workflow performs this sequence:

1. Check out the repository on the GitHub runner.
2. Create a temporary SSH private-key file.
3. Retry the EC2 SSH connection up to five times.
4. On EC2, fetch `origin/main` and hard-reset the deployment checkout to it.
5. Build and restart only the `app` Compose service.
6. Prune unused Docker resources.
7. Remove the runner's temporary key file.

Pushing `main` is therefore a production action. Require branch protection, successful validation, and review if the repository is operated by more than one maintainer.

## Post-deployment verification

Replace placeholders locally; never paste real keys into shared logs or shell history.

```bash
curl -i -H "X-Api-Key: $JNTUH_API_KEY" https://jntuhresults.dhethi.com/api/health
curl -fsS https://jntuhresults.dhethi.com/metrics > /dev/null
```

Then verify on the host:

```bash
docker-compose ps
docker-compose logs --tail=200 app
docker-compose exec rabbitmq rabbitmq-diagnostics ping
docker-compose exec redis redis-cli ping
docker-compose exec db pg_isready -U postgres
```

Confirm all of the following:

- API health returns 200 when the API key is supplied.
- `/metrics` is reachable by Prometheus.
- The normal and class queues have active consumers.
- A known cached result returns successfully.
- A controlled cache/database miss returns `202` and is later persisted by the worker.
- Prometheus targets are healthy and logs reach Loki.
- No scheduler or provider errors repeat continuously.

## Scaling constraints

- Every API replica starts a notification refresh loop. Only the daily job refresh is protected by a Redis lock.
- The worker is coupled to the API container in the current image, which limits independent scaling and restart control.
- Rate limiting uses shared Redis with an in-memory fail-open fallback.
- Class queue consumption is intentionally serial (`prefetch_count=1`).
- SQLite/local-process substitutes are not supported; both processes require consistent PostgreSQL, Redis, and RabbitMQ configuration.

If the API or worker must scale independently, split the image/process definitions first and update `architecture.md` and `RUNBOOK.md`.

## Rollback

Prefer a Git revert on `main` so the repository and deployed state remain aligned:

```bash
git revert <bad-commit-sha>
git push origin main
```

This triggers the normal deployment workflow. If the bad release included a database schema change, application rollback may not be sufficient; restore or migrate the database using the reviewed backup/recovery plan. Do not delete volumes or run broad Docker cleanup as a database recovery technique.

## Deployment incident handling

Use `RUNBOOK.md` for result misses, upstream outages, queue saturation, worker failure, Redis/PostgreSQL incidents, notification failures, and proof-storage problems.
