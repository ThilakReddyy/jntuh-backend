import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from subscriptions.firebase_notification import (
    _build_result_messages,
    _build_student_result_message,
    broadcast_result_notifications,
)
from scrapers.resultNotificationScraper import refresh_notifications


def test_build_result_message_matches_android_notification_contract():
    # No degree/regulation on this exam, so it takes the degenerate fallback
    # path: a single message on the global topic. This is the explicit
    # regression test that an unclassifiable release still reaches everyone.
    messages = _build_result_messages(
        {
            "title": "B.Tech IV Year II Semester Results",
            "link": "https://results.jntuh.ac.in/example",
        }
    )

    assert len(messages) == 1
    message = messages[0]
    assert message.topic == "result-updates"
    assert message.condition is None
    assert message.notification.title == "📢 JNTUH Results Released!"
    assert message.notification.body == "B.Tech IV Year II Semester Results"
    assert message.data == {
        "destination": "updates",
        "link": "https://results.jntuh.ac.in/example",
    }


def test_build_result_message_targets_degree_and_regulation_condition():
    messages = _build_result_messages(
        {
            "title": "B.Tech III Year I Semester (R18) Results",
            "link": "https://results.jntuh.ac.in/example",
            "degree": "btech",
            "regulation": "R18",
        }
    )

    assert len(messages) == 1
    message = messages[0]
    assert message.topic is None
    assert message.condition is not None
    for topic in (
        "result-updates",
        "result-updates-btech",
        "result-updates-r18",
        "result-updates-btech-r18",
    ):
        assert f"'{topic}' in topics" in message.condition


def test_build_result_message_falls_back_to_global_when_regulation_unparsed():
    messages = _build_result_messages(
        {
            "title": "B.Tech III Year I Semester Results",
            "link": "https://results.jntuh.ac.in/example",
            "degree": "btech",
            "regulation": "Set-1",
        }
    )

    assert len(messages) == 1
    message = messages[0]
    assert message.condition is not None
    assert "'result-updates' in topics" in message.condition
    assert "'result-updates-btech' in topics" in message.condition
    assert "-set-1" not in message.condition


def test_build_result_message_uses_global_topic_when_scoped_topics_disabled():
    with patch(
        "subscriptions.firebase_notification.FCM_SCOPED_TOPICS_ENABLED", False
    ):
        messages = _build_result_messages(
            {
                "title": "B.Tech III Year I Semester (R18) Results",
                "link": "https://results.jntuh.ac.in/example",
                "degree": "btech",
                "regulation": "R18",
            }
        )

    assert len(messages) == 1
    message = messages[0]
    assert message.topic == "result-updates"
    assert message.condition is None


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


def test_build_result_message_splits_multi_regulation_release_across_chunks():
    # 4 regulations x 2 topics each (regulation-only + degree+regulation) = 8
    # spillable topics, plus the pinned [global, degree] pair -> exceeds the
    # 5-topic FCM condition cap and must split into more than one message.
    messages = _build_result_messages(
        {
            "title": "B.Tech (R18, R16, R15, R13) Supplementary Results",
            "link": "https://results.jntuh.ac.in/example",
            "degree": "btech",
            "regulation": "R18, R16, R15, R13",
        }
    )

    assert len(messages) > 1
    for message in messages:
        assert message.topic is None
        assert message.condition is not None
        assert message.condition.count(" || ") <= 4  # at most 5 topics/condition

    all_conditions = " ".join(message.condition or "" for message in messages)
    assert all_conditions.count("'result-updates' in topics") == 1
    assert all_conditions.count("'result-updates-btech' in topics") == 1
    for regulation in ("r18", "r16", "r15", "r13"):
        assert f"'result-updates-{regulation}' in topics" in all_conditions
        assert f"'result-updates-btech-{regulation}' in topics" in all_conditions


def test_broadcast_sends_distinct_conditions_for_different_exams():
    exams = [
        {
            "title": "B.Tech III-I (R18) Results",
            "link": "https://example.com/btech",
            "degree": "btech",
            "regulation": "R18",
        },
        {
            "title": "M.Tech I-I (R22) Results",
            "link": "https://example.com/mtech",
            "degree": "mtech",
            "regulation": "R22",
        },
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
    assert len(sent_messages) == 2
    btech_condition, mtech_condition = (m.condition for m in sent_messages)
    assert "result-updates-btech" in btech_condition
    assert "result-updates-mtech" not in btech_condition
    assert "result-updates-mtech" in mtech_condition
    assert "result-updates-btech" not in mtech_condition


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
