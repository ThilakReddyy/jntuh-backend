import json
import time
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from config.redisConnection import redisConnection
from config.settings import QUEUE_NAME
from utils.logger import logger
from utils.helpers import isbpharmacyr22
from database.models import (
    studentAllResultsModel,
    studentBacklogs,
    studentDetailsModel,
    studentResultsModel,
)
from database.operations import get_students_details
from config.settings import RABBITMQ_CLASS_MAX_MESSAGES


async def fetch_class_results(app: FastAPI, roll_number: str, type: str):
    """Return results for an ENTIRE class section, derived from one roll number.

    The class is identified by the first 8 characters of the supplied roll
    number; internally the function also resolves the paired day/evening cohort
    by swapping the 5th char (rule: `5↔A` per JNTUH roll convention) so both
    cohorts appear in the response. The `type` parameter selects which
    per-student view is rendered:

    - `academicresult` (default) → consolidated mark sheet (same shape as
      `fetch_results`) — best-attempt-per-subject with SGPA/CGPA.
    - `allresult` → full per-attempt history (same shape as `fetch_all_results`).
    - `backlog` → backlogs-only (same shape as `fetch_backlogs`).

    Backpressure: if the RabbitMQ scrape queue depth exceeds
    `RABBITMQ_CLASS_MAX_MESSAGES` the response is HTTP 423 LOCKED so a class
    request can't pile a hundred scrapes onto an already-loaded server.
    Caching: Redis key `<class>Results+<type>` for 600 seconds.
    """

    # --- Step 1: RabbitMQ load check ---
    async with app.state.rabbitmq_connection.channel() as channel:
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        if queue.declaration_result.message_count > RABBITMQ_CLASS_MAX_MESSAGES:
            return JSONResponse(
                status_code=status.HTTP_423_LOCKED,
                content={
                    "status": "failure",
                    "message": "Server Load is High. Please Try again later!!",
                },
            )
    # --- Step 2: Redis cache lookup ---
    roll_results_key = f"{roll_number[:8]}Results+{type}"
    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_results_key)
        if cached_data:
            return json.loads(cached_data)  # pyright:ignore

    # --- Step 3: Determine roll_number2 ---
    def calculate_alt_roll_number(roll_number: str) -> str:
        if roll_number[4] != "5" and roll_number[5] == "A":
            first_two = str(int(roll_number[0:2]) + 1).zfill(2)
            return first_two + roll_number[2:4] + "5" + roll_number[5:8]
        else:
            first_two = str(int(roll_number[0:2]) - 1).zfill(2)
            return first_two + roll_number[2:4] + "1" + roll_number[5:8]

    roll_number2 = calculate_alt_roll_number(roll_number)
    is_bpharmacy = isbpharmacyr22(roll_number)

    # --- Step 4: Fetch student results ---
    start_time = time.perf_counter()
    students = await get_students_details(roll_number[:8], roll_number2[:8])
    logger.info(f"DB Query Time: {time.perf_counter() - start_time:.4f}s")

    results = []
    if students:
        for student in students:
            result = {"details": studentDetailsModel(student), "results": []}
            if student.marks:
                if type == "academicresult":
                    result["results"] = studentResultsModel(student.marks, is_bpharmacy)
                elif type == "allresult":
                    result["results"] = studentAllResultsModel(student.marks)
                elif type == "backlog":
                    result["results"] = studentBacklogs(student.marks, is_bpharmacy)
            results.append(result)

    # --- Step 5: Save to Redis cache ---
    if redisConnection.client:
        redisConnection.client.set(roll_results_key, json.dumps(results), ex=600)

    logger.info(f"Total class results  Time: {time.perf_counter() - start_time:.4f}s")

    return results
