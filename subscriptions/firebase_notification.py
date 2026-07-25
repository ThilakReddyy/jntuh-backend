import asyncio
from collections.abc import Mapping, Sequence
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import credentials, messaging

from config.settings import (
    FCM_RESULTS_TOPIC,
    FIREBASE_PROJECT_ID,
    GOOGLE_APPLICATION_CREDENTIALS,
)
from utils.logger import logger


_firebase_init_lock = Lock()
_FCM_BATCH_SIZE = 500


def _get_firebase_app():
    """Return the default Firebase app, initializing it on first use."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    if not GOOGLE_APPLICATION_CREDENTIALS:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not configured; "
            "Firebase result notifications are disabled"
        )

    with _firebase_init_lock:
        try:
            return firebase_admin.get_app()
        except ValueError:
            options = (
                {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
            )
            credential = credentials.Certificate(GOOGLE_APPLICATION_CREDENTIALS)
            return firebase_admin.initialize_app(credential, options)


def _build_result_message(exam: Mapping[str, Any]) -> messaging.Message:
    title = str(exam.get("title") or "A new JNTUH result is available").strip()
    link = str(
        exam.get("link") or "https://jntuhconnect.dhethi.com/academicresult"
    ).strip()

    return messaging.Message(
        notification=messaging.Notification(
            title="📢 JNTUH Results Released!",
            body=title,
        ),
        data={
            "destination": "updates",
            "link": link,
        },
        topic=FCM_RESULTS_TOPIC,
    )


def send_result_notification(exam: Mapping[str, Any]) -> str:
    """Send one result-release notification to the Android results topic."""
    message_id = messaging.send(
        _build_result_message(exam),
        app=_get_firebase_app(),
    )
    logger.info(f"Firebase result notification sent: {message_id}")
    return message_id


def _send_result_notifications(exams: Sequence[Mapping[str, Any]]) -> None:
    messages = [_build_result_message(exam) for exam in exams]
    if not messages:
        return

    app = _get_firebase_app()
    success_count = 0
    failure_count = 0
    for batch_start in range(0, len(messages), _FCM_BATCH_SIZE):
        response = messaging.send_each(
            messages[batch_start : batch_start + _FCM_BATCH_SIZE],
            app=app,
        )
        success_count += response.success_count
        failure_count += response.failure_count
        for batch_index, send_response in enumerate(response.responses):
            if not send_response.success:
                exam = exams[batch_start + batch_index]
                logger.error(
                    "Firebase result notification failed for "
                    f"{exam.get('title', 'unknown result')}: "
                    f"{send_response.exception}"
                )

    logger.info(
        "Firebase result notifications complete: "
        f"{success_count} sent, {failure_count} failed"
    )


async def broadcast_result_notifications(
    exams: Sequence[Mapping[str, Any]],
) -> None:
    """Send new result notifications without blocking the async scraper loop."""
    try:
        await asyncio.to_thread(_send_result_notifications, exams)
    except Exception as error:
        # A notification-provider outage must not undo the completed scrape or
        # prevent Telegram notifications from being sent.
        logger.error(f"Firebase result notification broadcast failed: {error}")
