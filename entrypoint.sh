#!/bin/sh
set -e

# Run Prisma migrations
prisma generate || true
prisma db push || true

# Start the FastAPI app
exec "$@"
