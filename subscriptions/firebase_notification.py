import asyncio
from collections.abc import Mapping, Sequence
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import credentials, messaging

from config.settings import (
    FCM_RESULTS_TOPIC,
    FCM_SCOPED_TOPICS_ENABLED,
    FIREBASE_PROJECT_ID,
    GOOGLE_APPLICATION_CREDENTIALS,
)
from subscriptions.topics import (
    normalize_regulations,
    partition_into_conditions,
    result_topic_condition,
    result_topics_for_exam,
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


def _build_result_messages(exam: Mapping[str, Any]) -> list[messaging.Message]:
    """Build the FCM message(s) for one newly-detected result release.

    Normally a single message. A release naming enough regulations to exceed
    FCM's 5-topics-per-condition cap is split into multiple messages, one per
    `partition_into_conditions` chunk (see subscriptions/topics.py).
    """
    title = str(exam.get("title") or "A new JNTUH result is available").strip()
    link = str(
        exam.get("link") or "https://jntuhconnect.dhethi.com/academicresult"
    ).strip()

    notification = messaging.Notification(
        title="📢 JNTUH Results Released!",
        body=title,
    )
    data = {
        "destination": "updates",
        "link": link,
    }

    if not FCM_SCOPED_TOPICS_ENABLED:
        return [
            messaging.Message(
                notification=notification, data=data, topic=FCM_RESULTS_TOPIC
            )
        ]

    regulation_raw = exam.get("regulation")
    if regulation_raw and not normalize_regulations(regulation_raw):
        logger.warning(
            f"Unrecognized regulation format for topic routing: {regulation_raw!r} "
            f"(exam: {title!r})"
        )

    topics, pinned_count = result_topics_for_exam(exam.get("degree"), regulation_raw)

    if len(topics) == 1:
        return [
            messaging.Message(
                notification=notification, data=data, topic=topics[0]
            )
        ]

    return [
        messaging.Message(
            notification=notification,
            data=data,
            condition=result_topic_condition(chunk),
        )
        for chunk in partition_into_conditions(topics, pinned_count)
    ]


def _build_student_result_message(
    roll_number: str, tokens: list[str]
) -> messaging.MulticastMessage:
    return messaging.MulticastMessage(
        notification=messaging.Notification(
            title="Your JNTUH results were updated",
            body=f"New result records are available for {roll_number}.",
        ),
        data={
            "destination": "student-result",
            "rollNumber": roll_number,
        },
        tokens=tokens,
    )


async def notify_student_result_updated(roll_number: str) -> None:
    """Notify only devices subscribed to this roll number."""
    from database.operations import (
        delete_result_device_subscriptions,
        get_result_device_subscriptions,
    )

    subscriptions = await get_result_device_subscriptions(roll_number, platform="android")
    if not subscriptions:
        return

    invalid_ids: list[str] = []
    app = _get_firebase_app()
    for batch_start in range(0, len(subscriptions), _FCM_BATCH_SIZE):
        batch = subscriptions[batch_start : batch_start + _FCM_BATCH_SIZE]
        response = await asyncio.to_thread(
            messaging.send_each_for_multicast,
            _build_student_result_message(
                roll_number, [record.deviceToken for record in batch]
            ),
            app=app,
        )
        for record, send_response in zip(batch, response.responses):
            if send_response.success:
                continue
            error_code = getattr(send_response.exception, "code", "")
            if error_code in {
                "messaging/registration-token-not-registered",
                "messaging/invalid-registration-token",
            }:
                invalid_ids.append(record.id)
            logger.error(
                f"Firebase student result notification failed for {roll_number}: "
                f"{send_response.exception}"
            )

    await delete_result_device_subscriptions(invalid_ids)


def send_result_notification(exam: Mapping[str, Any]) -> list[str]:
    """Send one result-release notification (as 1+ FCM messages) for an exam."""
    app = _get_firebase_app()
    message_ids = [
        messaging.send(message, app=app)
        for message in _build_result_messages(exam)
    ]
    logger.info(f"Firebase result notification(s) sent: {message_ids}")
    return message_ids


def _send_result_notifications(exams: Sequence[Mapping[str, Any]]) -> None:
    messages: list[messaging.Message] = []
    message_exams: list[Mapping[str, Any]] = []
    for exam in exams:
        for message in _build_result_messages(exam):
            messages.append(message)
            message_exams.append(exam)

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
                exam = message_exams[batch_start + batch_index]
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
