import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from subscriptions.firebase_notification import (
    _build_result_message,
    _build_student_result_message,
    broadcast_result_notifications,
)
from scrapers.resultNotificationScraper import refresh_notifications


def test_build_result_message_matches_android_notification_contract():
    message = _build_result_message(
        {
            "title": "B.Tech IV Year II Semester Results",
            "link": "https://results.jntuh.ac.in/example",
        }
    )

    assert message.topic == "result-updates"
    assert message.notification.title == "📢 JNTUH Results Released!"
    assert message.notification.body == "B.Tech IV Year II Semester Results"
    assert message.data == {
        "destination": "updates",
        "link": "https://results.jntuh.ac.in/example",
    }


def test_build_student_result_message_targets_only_subscribed_tokens():
    message = _build_student_result_message(
        "20J21A0101", ["first-device-token", "second-device-token"]
    )

    assert message.tokens == ["first-device-token", "second-device-token"]
    assert message.notification.title == "Your JNTUH results were updated"
    assert message.notification.body == (
        "New result records are available for 20J21A0101."
    )
    assert message.data == {
        "destination": "student-result",
        "rollNumber": "20J21A0101",
    }


def test_broadcast_sends_every_new_exam():
    exams = [
        {"title": "First result", "link": "https://example.com/first"},
        {"title": "Second result", "link": "https://example.com/second"},
    ]
    response = SimpleNamespace(
        responses=[
            SimpleNamespace(success=True, exception=None),
            SimpleNamespace(success=True, exception=None),
        ],
        success_count=2,
        failure_count=0,
    )

    with (
        patch(
            "subscriptions.firebase_notification._get_firebase_app",
            return_value=object(),
        ),
        patch(
            "subscriptions.firebase_notification.messaging.send_each",
            return_value=response,
        ) as send_each,
    ):
        asyncio.run(broadcast_result_notifications(exams))

    sent_messages = send_each.call_args.args[0]
    assert [message.notification.body for message in sent_messages] == [
        "First result",
        "Second result",
    ]


def test_refresh_broadcasts_only_newly_saved_exams():
    new_exams = [
        {
            "title": "New result",
            "link": "https://results.jntuh.ac.in/new-result",
        }
    ]
    broadcast = AsyncMock()

    with (
        patch(
            "scrapers.resultNotificationScraper.fetch_results",
            return_value=[object()],
        ),
        patch(
            "scrapers.resultNotificationScraper.parse_results",
            return_value=new_exams,
        ),
        patch(
            "scrapers.resultNotificationScraper.format_dates",
            return_value=new_exams,
        ),
        patch(
            "scrapers.resultNotificationScraper.get_exam_codes",
            return_value=new_exams,
        ),
        patch(
            "scrapers.resultNotificationScraper.save_exam_codes",
            new=AsyncMock(return_value=new_exams),
        ),
        patch("scrapers.resultNotificationScraper.send_telegram_notification"),
        patch(
            "scrapers.resultNotificationScraper.broadcast_result_notifications",
            new=broadcast,
        ),
    ):
        asyncio.run(refresh_notifications())

    broadcast.assert_awaited_once_with(new_exams)
