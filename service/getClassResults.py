import asyncio
import json
import string
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import QUEUE_NAME
from utils.helpers import isbpharmacyr22
from database.models import (
    studentAllResultsModel,
    studentBacklogs,
    studentDetailsModel,
    studentResultsModel,
)
from database.operations import get_details
from config.settings import RABBITMQ_CLASS_MAX_MESSAGES


async def fetch_class_results(app: FastAPI, roll_number: str, type: str):
    """Fetch student details and results from the database."""
    async with app.state.rabbitmq_connection.channel() as channel:
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        message_count = queue.declaration_result.message_count
        if message_count > RABBITMQ_CLASS_MAX_MESSAGES:
            return {
                "status": "failure",
                "message": "Server Load is High. Please Try again later!!",
            }

    roll_results_key = f"{roll_number[0:8]}Results+{type}"
    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_results_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    is_bpharmacy = isbpharmacyr22(roll_number)

    async def fetch_single(suffix: str):
        roll = roll_number[0:8] + suffix
        response = await get_details(roll)
        if response:
            student, marks = response
            if type == "academicresult":
                return {
                    "details": studentDetailsModel(student),
                    "results": studentResultsModel(marks, is_bpharmacy),
                }
            elif type == "allresult":
                return {
                    "details": studentDetailsModel(student),
                    "results": studentAllResultsModel(marks),
                }
            elif type == "backlog":
                return {
                    "details": studentDetailsModel(student),
                    "results": studentBacklogs(marks, is_bpharmacy),
                }

    numeric_suffixes = [str(i).zfill(2) for i in range(1, 100)]

    letter_suffixes = [
        f"{letter}{i}" for letter in string.ascii_uppercase for i in range(1, 10)
    ]

    all_suffixes = numeric_suffixes + letter_suffixes

    tasks = [fetch_single(suffix) for suffix in all_suffixes]
    results = await asyncio.gather(*tasks)

    if roll_number[4] != "5" and roll_number[5] == "A":
        first_two = str(int(roll_number[0:2]) + 1).zfill(2)
        roll_number = first_two + roll_number[2:4] + "5" + roll_number[5:8]
        tasks = [fetch_single(suffix) for suffix in numeric_suffixes]
        lateral_results = await asyncio.gather(*tasks)
        results.extend(lateral_results)

    responses = [r for r in results if r is not None]
    if redisConnection.client:
        redisConnection.client.set(
            roll_results_key, json.dumps(responses), ex=600
        )  # 10 minutes TTL

    return responses
