# Security Policy

## Supported version

Security fixes are applied to the current `main` branch. Older commits and independently modified deployments are not maintained as supported release lines.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability, leaked secret, authentication bypass, exposed student record, or vulnerable deployment detail.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting/security-advisory feature for this repository when available.
2. If private reporting is unavailable, contact the repository owner privately through the owner's GitHub profile and request a secure channel before sending sensitive details.

Include:

- A concise description and affected endpoint/component.
- Reproduction steps using synthetic data.
- Expected and observed impact.
- Relevant commit/version and deployment assumptions.
- A suggested mitigation, if known.

Never include real roll-number records, uploaded CMM documents, production tokens, private keys, service-account files, or exploit traffic against third-party JNTUH systems in a report.

## Security boundaries

### Public API guard

Most HTTP routes require `X-Api-Key`. This is an access gate, not user authentication:

- When `API_ACCESS_KEY` is unset, any non-empty header is accepted.
- Recognized Android/iOS User-Agents bypass the header for client compatibility.
- Browser clients may necessarily expose their API header value.

Do not use this guard to protect high-value administrative operations by itself. Admin grace-marks routes additionally require `GRACE_MARKS_ADMIN_KEY`; new privileged routes must use an equivalent server-side authorization boundary.

### MCP and chatbot

- MCP exposes only the read-only GET operation IDs in `config/mcp.py`.
- The chatbot receives that same bounded allowlist.
- Mutation, refresh, subscription, upload, and admin routes must remain excluded.
- Do not pass raw internal exception details or provider responses into model context or public responses.

### Student data

- Treat names, roll numbers, father names, marks, subscriptions, device tokens, and proof documents as sensitive data.
- Do not log complete uploaded documents, credentials, subscription payloads, or device tokens.
- Use synthetic records in tests and security reports.
- Limit database, log, and object-storage access to operators who require it.
- Define retention and deletion practices appropriate to the production deployment.

### Uploads and object storage

- Grace-marks proof uploads are limited by MIME type and size and must pass the configured CMM classifier before storage.
- Keep S3 buckets private; callers should receive expiring presigned URLs.
- Do not trust filenames as paths. Preserve filename sanitization and generated object keys.
- Gemini or storage failure must fail closed for new uploads.
- Treat the bundled CMM reference as sensitive project data and review replacements before committing them.

## Secret management

Never commit:

- `.env` or production environment exports.
- AWS/S3 credentials.
- Telegram tokens or chat identifiers.
- VAPID private keys.
- Firebase service-account JSON.
- APNs `.p8` files or inline private keys.
- Gemini/chat-provider keys.
- API/admin access keys.
- EC2 SSH private keys.

Store secrets in GitHub Actions secrets, the deployment platform's secret manager, or restricted host files outside the repository. Use separate development and production credentials.

If a secret is exposed:

1. Revoke or rotate it at the provider immediately.
2. Replace it in the deployment secret store.
3. Redeploy/restart affected services.
4. Review provider, API, and infrastructure logs for abuse.
5. Remove the value from Git history when necessary, while recognizing that history removal does not replace rotation.

## Dependency and image security

- Keep Python packages and container images reviewed and updated.
- Investigate GitHub/Dependabot alerts instead of suppressing them without analysis.
- Pin production images to reviewed versions or digests when reproducibility matters; the monitoring images currently use floating tags in places.
- Run tests after dependency updates, particularly auth, HTTP, Prisma, notification, and MCP tests.
- Rebuild images after rotating a secret only if the secret was incorrectly baked into an image; normally secrets should be injected at runtime.

## Deployment hardening

- Set `ENVIRONMENT=production` and a strong `API_ACCESS_KEY`.
- Use a strong, separate `GRACE_MARKS_ADMIN_KEY`.
- Restrict `/metrics`, RabbitMQ management, Grafana, Loki, PostgreSQL, Redis, and exporter ports at the network layer.
- Pin and verify the EC2 SSH host key; the current workflow disables strict host-key checking.
- Terminate TLS at Cloudflare/reverse proxy and secure traffic between infrastructure components where the environment requires it.
- Back up PostgreSQL and test restoration.
- Keep S3 public access blocked and grant only required object permissions.
- Review CORS origins and mobile User-Agent exemptions when adding clients.

## Safe security testing

Test only systems and accounts you own or are explicitly authorized to assess. Do not stress, scan, bypass, or exploit JNTUH or notification-provider infrastructure. Use local mocks and synthetic payloads for scraper and provider security tests.
