from config.redisConnection import redisConnection
from config.settings import EXPIRY_TIME
from database.operations import get_exam_codes
import json


async def load_exam_codes(degree, regulation):
    notificationkey = f"{degree}{regulation}notification"

    if redisConnection.client:
        cached_data = redisConnection.client.get(notificationkey)
        if cached_data:
            return json.loads(cached_data)  # pyright: ignore

    examcodes = await get_exam_codes(degree, regulation)
    if redisConnection.client:
        redisConnection.client.set(
            notificationkey, json.dumps(examcodes), ex=EXPIRY_TIME
        )

    return examcodes
