import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from config.redisConnection import redisConnection
from messaging.publisher import publish_class_results_message
from service.getClassResults import fetch_class_results


class _ChannelContext:
    def __init__(self, channel):
        self.channel = channel

    async def __aenter__(self):
        return self.channel

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


def test_publish_class_results_message_uses_dedicated_queue():
    exchange = SimpleNamespace(publish=AsyncMock())
    queue = SimpleNamespace(
        declaration_result=SimpleNamespace(message_count=4),
    )
    channel = SimpleNamespace(
        declare_queue=AsyncMock(return_value=queue),
        default_exchange=exchange,
    )
    connection = SimpleNamespace(
        channel=MagicMock(return_value=_ChannelContext(channel))
    )
    app = SimpleNamespace(state=SimpleNamespace(rabbitmq_connection=connection))

    published = asyncio.run(publish_class_results_message(app, "20J21A0101"))

    assert published is True
    channel.declare_queue.assert_awaited_once_with("classresults", durable=True)
    message = exchange.publish.await_args.args[0]
    assert message.body == b"20J21A0101"
    assert exchange.publish.await_args.kwargs["routing_key"] == "classresults"


def test_class_results_message_is_not_published_when_queue_has_five_messages():
    exchange = SimpleNamespace(publish=AsyncMock())
    queue = SimpleNamespace(
        declaration_result=SimpleNamespace(message_count=5),
    )
    channel = SimpleNamespace(
        declare_queue=AsyncMock(return_value=queue),
        default_exchange=exchange,
    )
    connection = SimpleNamespace(
        channel=MagicMock(return_value=_ChannelContext(channel))
    )
    app = SimpleNamespace(state=SimpleNamespace(rabbitmq_connection=connection))

    published = asyncio.run(publish_class_results_message(app, "20J21A0101"))

    assert published is False
    exchange.publish.assert_not_awaited()


def _class_results_app():
    queue = SimpleNamespace(
        declaration_result=SimpleNamespace(message_count=0),
    )
    channel = SimpleNamespace(declare_queue=AsyncMock(return_value=queue))
    connection = SimpleNamespace(
        channel=MagicMock(return_value=_ChannelContext(channel))
    )
    return SimpleNamespace(state=SimpleNamespace(rabbitmq_connection=connection))


def test_cached_class_results_are_not_published():
    cached_results = b'[{"cached": true}]'
    redis_client = SimpleNamespace(get=MagicMock(return_value=cached_results))
    publish = AsyncMock()

    with (
        patch.object(redisConnection, "client", redis_client),
        patch("service.getClassResults.publish_class_results_message", new=publish),
    ):
        result = asyncio.run(
            fetch_class_results(_class_results_app(), "20J21A0101", "academicresult")
        )

    assert result == [{"cached": True}]
    publish.assert_not_awaited()


def test_empty_class_results_cache_miss_is_not_published():
    redis_client = SimpleNamespace(
        get=MagicMock(return_value=None),
        set=MagicMock(),
    )
    publish = AsyncMock()

    with (
        patch.object(redisConnection, "client", redis_client),
        patch("service.getClassResults.publish_class_results_message", new=publish),
        patch(
            "service.getClassResults.get_students_details",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = asyncio.run(
            fetch_class_results(_class_results_app(), "20J21A0101", "academicresult")
        )

    assert result == []
    publish.assert_not_awaited()


def test_non_empty_database_class_results_are_published():
    redis_client = SimpleNamespace(
        get=MagicMock(return_value=None),
        set=MagicMock(),
    )
    publish = AsyncMock()
    student = SimpleNamespace(marks=[])

    with (
        patch.object(redisConnection, "client", redis_client),
        patch("service.getClassResults.publish_class_results_message", new=publish),
        patch(
            "service.getClassResults.get_students_details",
            new=AsyncMock(return_value=[student]),
        ),
        patch(
            "service.getClassResults.studentDetailsModel",
            return_value={"rollNo": "20J21A0101"},
        ),
    ):
        result = asyncio.run(
            fetch_class_results(_class_results_app(), "20J21A0101", "academicresult")
        )

    assert result == [
        {
            "details": {"rollNo": "20J21A0101"},
            "results": [],
        }
    ]
    publish.assert_awaited_once_with(ANY, "20J21A0101")


def test_class_results_response_survives_publish_failure():
    redis_client = SimpleNamespace(
        get=MagicMock(return_value=None),
        set=MagicMock(),
    )
    publish = AsyncMock(side_effect=RuntimeError("RabbitMQ publish failed"))
    student = SimpleNamespace(marks=[])

    with (
        patch.object(redisConnection, "client", redis_client),
        patch("service.getClassResults.publish_class_results_message", new=publish),
        patch(
            "service.getClassResults.get_students_details",
            new=AsyncMock(return_value=[student]),
        ),
        patch(
            "service.getClassResults.studentDetailsModel",
            return_value={"rollNo": "20J21A0101"},
        ),
    ):
        result = asyncio.run(
            fetch_class_results(_class_results_app(), "20J21A0101", "academicresult")
        )

    assert result == [
        {
            "details": {"rollNo": "20J21A0101"},
            "results": [],
        }
    ]
    redis_client.set.assert_called_once()
