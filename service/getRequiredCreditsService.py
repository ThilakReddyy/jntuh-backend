from fastapi import FastAPI
from config.redisConnection import redisConnection
import json

from config.settings import EXPIRY_TIME
from database.models import studentCredits, studentDetailsModel
from database.operations import get_details
from messaging.publisher import publish_message
from utils.helpers import get_credit_regulation_details, isbpharmacyr22


async def fetch_required_credits(app: FastAPI, roll_number: str):
    """Compute credits earned vs the regulation's required-credits table.

    Resolves the regulation/credits table for the roll number via
    `get_credit_regulation_details`, then returns a year-by-year breakdown:
    each academic year shows the two semesters' obtained credits, the year's
    cumulative `totalCredits`, plus an overall `totalObtainedCredits` and
    `totalRequiredCredits` so the caller can check whether the student is on
    track.

    B.Tech only — for other degrees / regulations the function returns
    `{status: "Failure", message: "..."}` without scraping. Caching: Redis key
    `<rollNo>RequiredCredits` for `EXPIRY_TIME` seconds; queues a scrape via
    `publish_message` on cache+DB miss.
    """
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
        details = studentDetailsModel(student)
        result = {
            "details": details,
            "results": studentCredits(
                marks, credits, isbpharmacyr22(details["rollNumber"])
            ),
        }

        if redisConnection.client:
            redisConnection.client.set(
                roll_credits_checker_key, json.dumps(result), ex=EXPIRY_TIME
            )

        # await publish_message(app, roll_number)

        return result

    return await publish_message(app, roll_number)
