import json
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from config.redisConnection import redisConnection
from scrapers.serverChecker import check_valid_url_in_redis
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
    """Return the CONSOLIDATED final mark sheet for a single student.

    For each subject the highest grade across all attempts (regular, supplementary,
    RCRV, Grace) is kept — so if a student failed the regular and cleared the
    supplementary, the supply grade wins. From that best-attempt set the response
    computes per-semester SGPA, semester credits, semester backlog count, an
    overall CGPA, total credits, and total backlogs. This is the right call for
    `What is this student's effective academic standing?`.

    For the raw per-attempt history use `fetch_all_results`; for only the still-
    failing subjects use `fetch_backlogs`. See `processResults` /
    `studentResultsModel` in database/models.py for the exact response shape.

    Caching: Redis key `<rollNo>Results` for `EXPIRY_TIME` seconds. The cached
    payload is augmented with a live `serverStatus` flag derived from
    `check_valid_url_in_redis` before returning. Falls back to a queued scrape
    via `publish_message` on cache+DB miss.
    """

    roll_results_key = f"{roll_number}Results"

    url = "."
    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_results_key)
        url = check_valid_url_in_redis()

        if cached_data:
            data = json.loads(cached_data)
            data["serverStatus"] = url != "."
            return data

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

        result["serverStatus"] = url != "."

        await publish_message(app, roll_number)

        return JSONResponse(status_code=status.HTTP_200_OK, content=result)

    return await publish_message(app, roll_number)
