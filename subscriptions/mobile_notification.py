import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from subscriptions.apns_notification import (
    broadcast_ios_result_notifications,
    notify_ios_student_result_updated,
)
from subscriptions.firebase_notification import (
    broadcast_result_notifications as broadcast_android_result_notifications,
    notify_student_result_updated as notify_android_student_result_updated,
)
from utils.logger import logger


async def broadcast_result_notifications(exams: Sequence[Mapping[str, Any]]) -> None:

    await broadcast_android_result_notifications(exams)
    await broadcast_ios_result_notifications(exams)


async def notify_student_result_updated(roll_number: str) -> None:
    results = await asyncio.gather(
        notify_android_student_result_updated(roll_number),
        notify_ios_student_result_updated(roll_number),
        return_exceptions=True,
    )
    for platform, result in zip(("Firebase", "APNs"), results):
        if isinstance(result, Exception):
            logger.error(
                f"{platform} student result notification failed for "
                f"{roll_number}: {result}"
            )
