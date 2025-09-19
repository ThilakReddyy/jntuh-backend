import asyncio
import json
import string
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
from database.operations import get_details, get_students_details
from config.settings import RABBITMQ_CLASS_MAX_MESSAGES


async def fetch_class_results(app: FastAPI, roll_number: str, type: str):
    """Fetch student details and results from the database."""
    # --- Step 1: Check RabbitMQ load ---
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

    is_bpharmacy = isbpharmacyr22(roll_number)

    async def get_student_results(roll_number):
        start_time = time.perf_counter()  # Start timer

        student_details = await get_students_details(roll_number[0:8])
        results = []
        if student_details:
            for student in student_details:
                result = {"details": studentDetailsModel(student), "results": []}
                if student.marks:
                    marks = []
                    if type == "academicresult":
                        marks = studentResultsModel(student.marks, is_bpharmacy)
                    elif type == "allresult":
                        marks = studentAllResultsModel(student.marks)

                    elif type == "backlog":
                        marks = studentBacklogs(student.marks, is_bpharmacy)

                    result["results"] = marks
                    results.append(result)
        end_time = time.perf_counter()
        logger.info(f"Class Results Query took {end_time - start_time:.4f} seconds")
        return results

    results = await get_student_results(roll_number)
    if roll_number[4] != "5" and roll_number[5] == "A":
        first_two = str(int(roll_number[0:2]) + 1).zfill(2)
        roll_number = first_two + roll_number[2:4] + "5" + roll_number[5:8]
        eresults = await get_student_results(roll_number)
        results.extend(eresults)

    if redisConnection.client:
        redisConnection.client.set(roll_results_key, json.dumps(results), ex=600)
    return results
