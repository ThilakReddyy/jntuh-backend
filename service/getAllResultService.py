from datetime import datetime
import json
from typing import List

from config.redisConnection import redisConnection
from prisma.models import student, mark
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
        studentDetail, marks = response
        result = {
            "details": studentDetailsModel(studentDetail),
            "results": studentAllResultsModel(marks),
        }
        if redisConnection.client:
            redisConnection.client.set(roll_all_key, json.dumps(result), ex=EXPIRY_TIME)

        # await publish_message(app, roll_number)

        return result

    return await publish_message(app, roll_number)
