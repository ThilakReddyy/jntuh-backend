"""Seed the AcademicCalendar and Syllabus tables from the static JSON in seed_data/.

The JSON files are generated from the web frontend's TypeScript constants by
`seed_data/generate.mjs`. This script wipes both tables and re-inserts, so it is
idempotent — safe to run repeatedly.

Prerequisites (run from the repo root, with the venv active):
    prisma generate      # regenerate the client after schema changes
    prisma db push       # create the academic_calendar and syllabus tables
    python prisma/seed.py
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from prisma import Prisma

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data")
BATCH_SIZE = 500

# Load DATABASE_URL (and friends) from the repo-root .env for the Prisma client.
load_dotenv(os.path.join(ROOT, ".env"))


def _load(name: str):
    with open(os.path.join(SEED_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


async def _seed(model, rows, label: str):
    await model.delete_many()
    created = 0
    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start : start + BATCH_SIZE]
        created += await model.create_many(data=chunk)
    print(f"Seeded {created} {label} rows")


async def main():
    calendars = _load("calendars.json")
    syllabus = _load("syllabus.json")

    db = Prisma()
    await db.connect()
    try:
        await _seed(db.academiccalendar, calendars, "academic_calendar")
        await _seed(db.syllabus, syllabus, "syllabus")
    finally:
        await db.disconnect()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
