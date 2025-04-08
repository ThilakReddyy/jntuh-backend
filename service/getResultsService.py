import json
from fastapi import FastAPI
from config.redisConnection import redisConnection
from utils.helpers import isbpharmacyr22
from utils.logger import redis_logger
from config.settings import EXPIRY_TIME
from database.models import (
    studentDetailsModel,
    studentResultsModel,
)
from database.operations import get_details
from messaging.publisher import publish_message


async def fetch_results(app: FastAPI, roll_number: str):
    """Fetch student details and results from the database."""

    roll_results_key = f"{roll_number}Results"
    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_results_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    response = await get_details(roll_number)
    if response:
        student, marks = response
        result = {
            "details": studentDetailsModel(student),
            "results": studentResultsModel(marks, isbpharmacyr22(roll_number)),
        }

        if redisConnection.client:
            redisConnection.client.set(
                roll_results_key, json.dumps(result), ex=EXPIRY_TIME
            )
        else:
            redis_logger.warning(f"Unable to connect to redis {roll_number}")

        await publish_message(app, roll_number)

        return result

    return await publish_message(app, roll_number)
