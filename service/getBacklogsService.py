import json
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import EXPIRY_TIME
from database.models import (
    studentBacklogs,
    studentDetailsModel,
)
from database.operations import get_details
from messaging.publisher import publish_message


async def fetch_backlogs(app: FastAPI, roll_number: str):
    """Fetch student details and results from the database."""

    roll_backlogs_key = f"{roll_number}Backlogs"

    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_backlogs_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore
    response = await get_details(roll_number)
    if response:
        student, marks = response
        result = {
            "details": studentDetailsModel(student),
            "results": studentBacklogs(marks),
        }

        if redisConnection.client:
            redisConnection.client.set(
                roll_backlogs_key, json.dumps(result), ex=EXPIRY_TIME
            )

        await publish_message(app, roll_number)

        return result

    return await publish_message(app, roll_number)
