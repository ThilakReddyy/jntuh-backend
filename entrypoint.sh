#!/bin/sh
set -e

# Run Prisma migrations
prisma generate || true
prisma db push || true

# Start the FastAPI app
exec "$@"

# Start FastAPI in the background
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 &

# Start main2.py in the foreground (so container doesn't exit)
python main2.py
