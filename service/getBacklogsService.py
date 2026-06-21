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
    """Return only the subjects this student has NOT yet cleared across any attempt.

    Internally builds the consolidated (best-attempt-per-subject) view and then
    filters down to subjects whose best grade is still F or Ab. The response
    contains only the failing semesters, only the failing subjects within those
    semesters, and a `totalBacklogs` count.

    Distinct from `fetch_results` (which returns every subject) and from
    `grace_marks_service.check_eligibility` (which uses the backlog list as input
    to decide grace eligibility). Honors B.Pharm R22 grading via `isbpharmacyr22`.

    Caching: Redis key `<rollNo>Backlogs` for `EXPIRY_TIME` seconds; queues a
    scrape via `publish_message` on cache+DB miss.
    """

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
