#!/usr/bin/env bash
set -euo pipefail
# Older EC2 hosts may only have the legacy `docker-compose` command.
# Install a supported CLI plugin before using any Compose-specific flags.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."
python3 scripts/ensure_compose.py
# Keep the existing Compose project name: changing it changes volume names.
export APP_VERSION="${APP_VERSION:-$(git rev-parse --short HEAD)}"
docker compose config --quiet
docker compose build app
# Apply configuration changes to the entire stack, including exporters/worker.
# db push refuses destructive schema changes unless explicitly accepted.
docker compose up -d --wait --wait-timeout 240
# Mounted config file content alone does not trigger a Compose recreation.
docker compose up -d --force-recreate --no-deps --wait --wait-timeout 120 prometheus loki tempo alloy grafana
python3 scripts/observability_smoke.py --skip-results
