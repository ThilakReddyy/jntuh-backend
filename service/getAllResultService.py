import json

from config.redisConnection import redisConnection
from config.settings import EXPIRY_TIME
from database.models import studentAllResultsModel, studentDetailsModel
from database.operations import get_details
from fastapi import FastAPI
from messaging.publisher import publish_message


async def fetch_all_results(app: FastAPI, roll_number: str):
    """Fetch student details and results from the database, using Redis cache when possible."""

    roll_all_key = f"{roll_number}ALL"

    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_all_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    response = await get_details(roll_number)

    if response:
        student, marks = response
        result = {
            "details": studentDetailsModel(student),
            "results": studentAllResultsModel(marks),
        }

        if redisConnection.client:
            redisConnection.client.set(roll_all_key, json.dumps(result), ex=EXPIRY_TIME)

        return result

    return await publish_message(app, roll_number)

