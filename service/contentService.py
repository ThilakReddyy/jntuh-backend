"""Read-through services for the static content tables (academic calendars, syllabus).

Both endpoints rebuild the flat DB rows into the nested tree shape the web frontend
already renders, and cache the built tree in Redis for `CONTENT_EXPIRY_TIME` seconds
(the content changes rarely). See `prisma/seed.py` for how the tables are populated.
"""

import json

from config.connection import prismaConnection
from config.redisConnection import redisConnection
from config.settings import (
    CALENDARS_REDIS_KEY,
    CONTENT_EXPIRY_TIME,
    SYLLABUS_REDIS_KEY,
)


async def getCalendars():
    """Return calendars as `{ academicYear: { degree: { studyYear: { title: link } } } }`."""
    if redisConnection.client:
        cached = redisConnection.client.get(CALENDARS_REDIS_KEY)
        if cached:
            return json.loads(cached)  # pyright: ignore

    rows = await prismaConnection.prisma.academiccalendar.find_many(
        order=[
            {"academicYear": "desc"},
            {"degree": "asc"},
            {"studyYear": "asc"},
        ]
    )

    tree: dict = {}
    for r in rows:
        (
            tree.setdefault(r.academicYear, {})
            .setdefault(r.degree, {})
            .setdefault(r.studyYear, {})
        )[r.title] = r.link

    if redisConnection.client:
        redisConnection.client.set(
            CALENDARS_REDIS_KEY, json.dumps(tree), ex=CONTENT_EXPIRY_TIME
        )
    return tree


async def getSyllabus():
    """Return syllabus as `{ degree: { regulation: { category: [ {title, link} ] } } }`.

    Rows with an empty regulation collapse to `{ degree: { category: [...] } }` — the
    frontend's tree walker handles the variable depth transparently.
    """
    if redisConnection.client:
        cached = redisConnection.client.get(SYLLABUS_REDIS_KEY)
        if cached:
            return json.loads(cached)  # pyright: ignore

    rows = await prismaConnection.prisma.syllabus.find_many(
        order=[
            {"degree": "asc"},
            {"regulation": "desc"},
            {"category": "asc"},
            {"title": "asc"},
        ]
    )

    tree: dict = {}
    for r in rows:
        node = tree.setdefault(r.degree, {})
        if r.regulation:
            node = node.setdefault(r.regulation, {})
        node.setdefault(r.category, []).append({"title": r.title, "link": r.link})

    if redisConnection.client:
        redisConnection.client.set(
            SYLLABUS_REDIS_KEY, json.dumps(tree), ex=CONTENT_EXPIRY_TIME
        )
    return tree
