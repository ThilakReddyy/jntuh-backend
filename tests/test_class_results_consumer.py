import asyncio
from unittest.mock import AsyncMock, call, patch

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
    process = AsyncMock()

    with patch("messaging.consumer.process_message", new=process):
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
