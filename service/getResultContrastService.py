from fastapi import FastAPI
from config.redisConnection import redisConnection
import json

from config.settings import EXPIRY_TIME
from database.models import (
    studentDetailsModel,
    studentResultContrast,
    studentResultsModel,
)
from database.operations import get_details
from messaging.publisher import publish_message


async def fetch_result_contrast(app: FastAPI, roll_number_1: str, roll_number_2: str):
    roll_result_contrast_key = f"{roll_number_1}{roll_number_2}ResultContrast"

    if redisConnection.client:
        cached_data = redisConnection.client.get(roll_result_contrast_key)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    response1 = await get_details(roll_number_1)
    response2 = await get_details(roll_number_2)
    if response1 is None or response2 is None:
        if response1 is None:
            return await publish_message(app, roll_number_1)
        if response2 is None:
            return await publish_message(app, roll_number_2)

    if response1 and response2:
        student1, marks1 = response1
        student2, marks2 = response2
        result1 = {
            "details": studentDetailsModel(student1),
            "results": studentResultsModel(marks1),
        }
        result2 = {
            "details": studentDetailsModel(student2),
            "results": studentResultsModel(marks2),
        }
        finalResult = studentResultContrast(result1, result2)
        if redisConnection.client:
            redisConnection.client.set(
                roll_result_contrast_key, json.dumps(finalResult), ex=EXPIRY_TIME
            )

        return finalResult
