from fastapi import FastAPI
from config.redisConnection import redisConnection

from messaging.publisher import publish_message


async def fetch_results_using_hard_refresh(app: FastAPI, roll_number: str):
    roll_credits_checker_key = f"{roll_number}RequiredCredits"
    roll_backlogs_key = f"{roll_number}Backlogs"
    roll_all_key = f"{roll_number}ALL"
    roll_results_key = f"{roll_number}Results"

    if redisConnection.client:
        redisConnection.client.delete(roll_credits_checker_key)
        redisConnection.client.delete(roll_backlogs_key)
        redisConnection.client.delete(roll_all_key)
        redisConnection.client.delete(roll_results_key)

    return await publish_message(app, roll_number)
