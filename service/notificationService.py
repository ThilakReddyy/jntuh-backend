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
    """Get Notifications"""
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
    return await publish_message(app, NOTIFICATIONS_REDIS_KEY)
