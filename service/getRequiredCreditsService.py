from fastapi import FastAPI
from config.redisConnection import redisConnection
import json
import time

from config.settings import EXPIRY_TIME
from database.models import studentBacklogs, studentCredits, studentDetailsModel
from database.operations import get_details
from messaging.publisher import publish_message
from utils.helpers import get_credit_regulation_details


async def fetch_required_credits(app: FastAPI, roll_number: str):
    roll_credits_checker_key = f"{roll_number}RequiredCredits"

    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_credits_checker_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    credits = get_credit_regulation_details(roll_number)
    if credits is None:
        return {
            "status": "Failure",
            "message": "This feature is only applicable for btech students currently!!",
        }

    response = await get_details(roll_number)
    if response:
        student, marks = response
        result = {
            "details": studentDetailsModel(student),
            "results": studentCredits(marks, credits),
        }

        if redisConnection.client:
            redisConnection.client.set(
                roll_credits_checker_key, json.dumps(result), ex=EXPIRY_TIME
            )

        await publish_message(app, roll_number)

        return result

    return await publish_message(app, roll_number)
