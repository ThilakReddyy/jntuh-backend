import json
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import NOTIFICATIONS_REDIS_KEY
from messaging.publisher import publish_message


async def notification(app: FastAPI):
    """Get Notifications"""
    try:
        if redisConnection.client:
            cached_data = redisConnection.client.get(NOTIFICATIONS_REDIS_KEY)
            if cached_data:
                return json.loads(cached_data)  # pyright: ignore

        return await publish_message(app, NOTIFICATIONS_REDIS_KEY)
    except Exception:
        return {"status": "failure", "message": "Unexpected error has occured"}
