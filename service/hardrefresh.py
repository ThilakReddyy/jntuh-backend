from fastapi import FastAPI

from messaging.publisher import publish_message
from utils.caching import invalidate_all_cache


async def fetch_results_using_hard_refresh(app: FastAPI, roll_number: str):
    invalidate_all_cache(roll_number)
    return await publish_message(app, roll_number)
