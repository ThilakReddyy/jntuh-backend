import json
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import FIVE_MINUTE_EXPIRY, NOTIFICATIONS_REDIS_KEY
from database.operations import get_notifications
from messaging.publisher import publish_message


async def notification(
    app: FastAPI, page: int, regulation: str, degree: str, year: str, title: str
):
    """Get Notifications"""
    try:
        key = NOTIFICATIONS_REDIS_KEY + str(page) + regulation + degree + year + title
        if redisConnection.client:
            cached_data = redisConnection.client.get(key)
            if cached_data:
                return json.loads(cached_data)  # pyright: ignore

        results = await get_notifications(page, regulation, degree, year, title)
        if redisConnection.client:
            redisConnection.client.set(key, json.dumps(results), ex=FIVE_MINUTE_EXPIRY)
        return results

    except Exception:
        return {"status": "failure", "message": "Unexpected error has occured"}


async def refreshNotification(app: FastAPI):
    return await publish_message(app, NOTIFICATIONS_REDIS_KEY)
