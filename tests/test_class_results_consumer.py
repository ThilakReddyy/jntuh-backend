import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from config.redisConnection import redisConnection
from messaging.consumer import (
    iter_class_roll_numbers,
    process_class_results_message,
)


def test_iter_class_roll_numbers_increments_year_for_regular_cohort():
    roll_numbers = list(iter_class_roll_numbers("18E51A0479"))

    assert len(roll_numbers) == 718
    assert roll_numbers[:2] == ["18E51A0401", "18E51A0402"]
    assert roll_numbers[98:101] == [
        "18E51A0499",
        "18E51A04A0",
        "18E51A04A1",
    ]
    assert roll_numbers[358:361] == [
        "18E51A04Z9",
        "19E55A0401",
        "19E55A0402",
    ]
    assert roll_numbers[-1] == "19E55A04Z9"


def test_iter_class_roll_numbers_decrements_year_for_lateral_cohort():
    roll_numbers = list(iter_class_roll_numbers("19E55A0479"))

    assert roll_numbers[0] == "19E55A0401"
    assert roll_numbers[358] == "19E55A04Z9"
    assert roll_numbers[359] == "18E51A0401"
    assert roll_numbers[-1] == "18E51A04Z9"


def test_process_class_results_message_processes_roll_numbers_in_order():
    process = AsyncMock(return_value=True)
    redis_client = SimpleNamespace(
        exists=MagicMock(return_value=False),
        set=MagicMock(),
    )

    with (
        patch("messaging.consumer.process_message", new=process),
        patch.object(redisConnection, "client", redis_client),
    ):
        asyncio.run(process_class_results_message("18E51A0479"))

    assert process.await_count == 718
    assert process.await_args_list[:3] == [
        call("18E51A0401"),
        call("18E51A0402"),
        call("18E51A0403"),
    ]
    assert process.await_args_list[-2:] == [
        call("19E55A04Z8"),
        call("19E55A04Z9"),
    ]
    assert redis_client.set.call_args_list == [
        call("class_results_processed:18E51A04", "1", ex=86400),
        call("class_results_processed:19E55A04", "1", ex=86400),
    ]


def test_process_class_results_message_skips_recently_processed_class():
    process = AsyncMock()
    redis_client = SimpleNamespace(
        # The paired cohort was processed, so this request represents the same class.
        exists=MagicMock(side_effect=[False, True]),
        set=MagicMock(),
    )

    with (
        patch("messaging.consumer.process_message", new=process),
        patch.object(redisConnection, "client", redis_client),
    ):
        asyncio.run(process_class_results_message("18E51A0479"))

    process.assert_not_awaited()
    redis_client.set.assert_not_called()


def test_process_class_results_message_stops_after_twenty_consecutive_empty_rolls():
    process = AsyncMock(return_value=False)
    redis_client = SimpleNamespace(
        exists=MagicMock(return_value=False),
        set=MagicMock(),
    )

    with (
        patch("messaging.consumer.process_message", new=process),
        patch.object(redisConnection, "client", redis_client),
    ):
        asyncio.run(process_class_results_message("18E51A0479"))

    assert process.await_count == 20
    assert process.await_args_list[-1] == call("18E51A0420")
    assert redis_client.set.call_args_list == [
        call("class_results_processed:18E51A04", "1", ex=86400),
        call("class_results_processed:19E55A04", "1", ex=86400),
    ]


def test_non_empty_result_resets_consecutive_empty_roll_count():
    process = AsyncMock(side_effect=([False] * 19) + [True] + ([False] * 20))
    redis_client = SimpleNamespace(
        exists=MagicMock(return_value=False),
        set=MagicMock(),
    )

    with (
        patch("messaging.consumer.process_message", new=process),
        patch.object(redisConnection, "client", redis_client),
    ):
        asyncio.run(process_class_results_message("18E51A0479"))

    assert process.await_count == 40
    assert process.await_args_list[-1] == call("18E51A0440")
