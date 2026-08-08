# Contributing to JNTUH Results Backend

Thank you for improving the project. Student-result correctness and availability take priority over supporting features, so changes to scraping, grading, caching, persistence, or queue behavior require focused tests and documentation.

## Before you start

Read:

- `README.md` for the result read path and public capabilities.
- `architecture.md` for component boundaries, data flows, and invariants.
- `SECURITY.md` before handling authentication, uploads, secrets, dependencies, or student data.
- `RUNBOOK.md` when changing behavior operators rely on during incidents.

Use an issue or design discussion before making a breaking API change, changing a Prisma uniqueness constraint, or altering the result projection rules.

## Prerequisites

- Python 3.11
- Docker and Docker Compose
- PostgreSQL, Redis, and RabbitMQ (the Compose services are the simplest local option)
- Prisma CLI installed through `requirements.txt`

The committed Compose file provides infrastructure services, but its `app` service is commented out. Run the Python processes on the host unless you intentionally provide an application override.

## Local setup

```bash
git clone https://github.com/ThilakReddyy/jntuh-backend.git
cd jntuh-backend

python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
docker-compose up -d db redis rabbitmq

prisma generate
prisma db push
```

Replace every required placeholder in `.env`. The settings module exits during import when a startup-required value is absent. Do not commit `.env`, cloud credentials, notification-provider credentials, `.p8` files, service-account JSON, or real student data.

Run the API and worker in separate terminals:

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
source venv/bin/activate
python main2.py
```

The worker is necessary for a cache-and-database miss to progress beyond `202 Accepted`.

## Validation

Run the checks relevant to your change before opening a pull request:

```bash
python -m pytest -q
pyright
python -m compileall -q main.py main2.py api service messaging database scrapers subscriptions chatbot config utils
```

Load testing is optional unless the change affects hot result paths, cache behavior, class requests, or queue publishing:

```bash
locust -f tests/locustfile.py --host http://localhost:8000
```

At the current revision, one RabbitMQ publisher test and the configured class-queue limit disagree: the test accepts a fourth queued message, while production rejects at the configured limit of 3. Do not hide new failures behind that known mismatch, and update the test and constant together if your change resolves it.

## Development rules

### Result behavior

- Preserve raw exam attempts in PostgreSQL; derive consolidated responses in model/service code.
- Use `validateRollNo` for public roll-number inputs.
- Use `isbpharmacyr22()` consistently for B.Pharm R22 grade-point calculation.
- Keep regular, supplementary, RCRV, and grace attempts distinct.
- A result cache addition must have an explicit invalidation or TTL strategy.
- A database miss should queue work and return promptly instead of scraping inside the request.

### Queues and workers

- Keep publisher thresholds and tests synchronized.
- Do not remove backpressure to make a failing load test pass.
- Preserve normal/class queue isolation and prefetch behavior unless the operational impact is understood.
- Make message processing idempotent; retries or duplicate messages must not create duplicate mark attempts.

### API and MCP

- Keep existing operation IDs stable unless a deliberate breaking change is approved.
- Do not expose mutations or admin routes through MCP.
- Add tests when changing header-guard exemptions, mobile User-Agent handling, rate limits, admin authentication, or OpenAPI security metadata.
- Avoid returning provider credentials, internal exception bodies, or student data in logs.

### Database schema

After editing `prisma/schema.prisma`:

```bash
prisma generate
prisma db push
```

Review the generated database change for data-loss risk before applying it outside development. Preserve uniqueness and indexes needed by result ingestion.

### Documentation

Update documentation in the same pull request when behavior changes:

- `README.md`: public capabilities, setup, and read-path summary.
- `architecture.md`: components, flows, invariants, and data model.
- `DEPLOYMENT.md`: runtime, environment, or release changes.
- `RUNBOOK.md`: new alerts, failure modes, or recovery steps.
- `SECURITY.md`: authentication, secrets, upload, or disclosure policy.
- `CLAUDE.md`: repository guidance for coding agents.

## Pull request workflow

1. Branch from the current `main`.
2. Keep the change focused and avoid committing unrelated local files.
3. Add or update tests for observable behavior.
4. Run the relevant validation commands.
5. Explain what changed, why, operational impact, schema/config changes, and validation results.
6. Call out known limitations rather than silently changing or ignoring them.

Suggested branch names are `feature/<short-name>`, `fix/<short-name>`, and `docs/<short-name>`.

## Review checklist

- Result projections remain correct across regular, supplementary, RCRV, grace, and B.Pharm R22 cases.
- Cache keys and invalidation are consistent.
- Queue changes retain bounded load.
- New environment variables are documented and safely optional or startup-validated.
- No credentials, uploaded documents, generated logs, or personal student records are included.
- Tests and documentation describe the implementation that will actually run.

## License

Contributions are accepted under the repository's GPL-3.0 license.
