import json
from config.redisConnection import getRedisKeyValue, redisConnection
from config.settings import EXPIRY_TIME
from database.models import studentAllResultsModel, studentDetailsModel
from database.operations import get_details
from fastapi import FastAPI
from messaging.publisher import publish_message


async def fetch_all_results(app: FastAPI, roll_number: str):
    """Return the COMPLETE attempt history for a single student, grouped per semester.

    Each semester contains a list of exams (regular, supplementary, RCRV-revaluation,
    Grace) and each exam holds the subject grades exactly as recorded for that
    attempt — nothing is collapsed or deduplicated. Use this when the caller wants
    to see EVERY attempt, including failed regulars later cleared via supplementary.

    Do NOT use this for SGPA / CGPA or the effective mark sheet — call
    `fetch_results` (the consolidated view) for that. See `studentAllResultsModel`
    in database/models.py for the exact response shape.

    Caching: Redis key `<rollNo>ALL` for `EXPIRY_TIME` seconds. On cache+DB miss the
    scrape is queued via RabbitMQ (`publish_message`) and a pending response is
    returned to the caller.
    """

    roll_all_key = f"{roll_number}ALL"

    response = getRedisKeyValue(roll_all_key)
    if response is not None:
        return json.loads(response)  # pyright: ignore

    response = await get_details(roll_number)

    if response:
        studentDetail, marks = response
        result = {
            "details": studentDetailsModel(studentDetail),
            "results": studentAllResultsModel(marks),
        }
        if redisConnection.client:
            redisConnection.client.set(roll_all_key, json.dumps(result), ex=EXPIRY_TIME)

        return result

    return await publish_message(app, roll_number)
