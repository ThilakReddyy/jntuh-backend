import json
from fastapi import FastAPI
from config.redisConnection import getRedisKeyValue, redisConnection
from config.settings import EXPIRY_TIME
from database.models import (
    studentBacklogs,
    studentDetailsModel,
)
from database.operations import get_details
from messaging.publisher import publish_message
from utils.helpers import isbpharmacyr22


async def fetch_backlogs(app: FastAPI, roll_number: str):
    """Fetch student details and results from the database."""

    roll_backlogs_key = f"{roll_number}Backlogs"

    response = getRedisKeyValue(roll_backlogs_key)
    if response is not None:
        return json.loads(response)  # pyright: ignore

    response = await get_details(roll_number)
    if response:
        student, marks = response
        details = studentDetailsModel(student)
        result = {
            "details": details,
            "results": studentBacklogs(marks, isbpharmacyr22(details["rollNumber"])),
        }

        if redisConnection.client:
            redisConnection.client.set(
                roll_backlogs_key, json.dumps(result), ex=EXPIRY_TIME
            )

        return result

    return await publish_message(app, roll_number)
