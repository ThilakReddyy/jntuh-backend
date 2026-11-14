import json
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from config.redisConnection import redisConnection
from config.settings import (
    FIVE_MINUTE_EXPIRY,
    LATEST_NOTIFICATIONS_REDIS_KEY,
    NOTIFICATIONS_REDIS_KEY,
)
from database.operations import get_latest_notifications, get_notifications
from messaging.publisher import publish_message


async def notification(
    page: int, category: str, regulation: str, degree: str, year: str, title: str
):
    """Return paginated JNTUH result notifications, filterable by metadata.

    Filters: `regulation`, `degree`, `year`, and a substring `title` are passed
    through to `get_notifications`. The `category` arg is a coarse gate — only
    `results` or `all` are honored; any other category returns an empty list
    immediately without hitting the DB. Use this for the filterable browsing
    feed; for the homepage `latest` strip use `getLatestNotifications`.

    Caching: Redis key `<NOTIFICATIONS_REDIS_KEY><page><regulation><degree><year><title>`
    for `FIVE_MINUTE_EXPIRY` seconds. Catches all exceptions and returns
    HTTP 500 with a generic message.
    """
    try:
        if category.lower() != "results" and category.lower() != "all":
            print(category)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=[],
            )
        key = NOTIFICATIONS_REDIS_KEY + str(page) + regulation + degree + year + title
        if redisConnection.client:
            cached_data = redisConnection.client.get(key)
            if cached_data:
                return json.loads(cached_data)  # pyright: ignore

        results = await get_notifications(page, regulation, degree, year, title)
        if redisConnection.client:
            redisConnection.client.set(key, json.dumps(results), ex=FIVE_MINUTE_EXPIRY)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=results,
        )

    except Exception:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Unexpected Error has occured"},
        )


async def getLatestNotifications():
    """Return the most-recent result notifications across all categories — the homepage feed.

    No filters and no pagination — this is the small, always-fresh strip the
    UI shows above the fold. For a filterable / paginated browse use
    `notification`. Caching: Redis key `LATEST_NOTIFICATIONS_REDIS_KEY` for
    `FIVE_MINUTE_EXPIRY` seconds. Catches all exceptions and returns HTTP 500
    with a generic message.
    """
    try:
        key = LATEST_NOTIFICATIONS_REDIS_KEY
        if redisConnection.client:
            cached_data = redisConnection.client.get(key)
            if cached_data:
                return json.loads(cached_data)  # pyright: ignore

        results = await get_latest_notifications()
        if redisConnection.client:
            redisConnection.client.set(key, json.dumps(results), ex=FIVE_MINUTE_EXPIRY)
        return results

    except Exception:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failure",
                "message": "Unexpected Error has occured",
            },
        )


async def refreshNotification(app: FastAPI):
    """Admin-only: enqueue a full notifications-scrape via RabbitMQ.

    Publishes a message with key `NOTIFICATIONS_REDIS_KEY` so the scraper
    worker re-fetches and warms the notifications cache. Hidden from the
    OpenAPI schema and not exposed over MCP — callers other than the admin/
    scheduler should use `notification` or `getLatestNotifications` instead.
    """
    return await publish_message(app, NOTIFICATIONS_REDIS_KEY)
