from config.redisConnection import redisConnection
from config.settings import EXPIRY_TIME
from database.operations import get_exam_codes
import json


async def load_exam_codes(degree, regulation):
    examcodeskey = f"{degree}{regulation}keys"

    if redisConnection.client:
        cached_data = redisConnection.client.get(examcodeskey)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    examcodes = await get_exam_codes(degree, regulation)
    if redisConnection.client:
        redisConnection.client.set(examcodeskey, json.dumps(examcodes), ex=EXPIRY_TIME)

    return examcodes
