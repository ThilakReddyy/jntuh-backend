import asyncio
from unittest.mock import AsyncMock, patch

from service.subscriptionService import delete_result_subscriptions


def test_delete_result_subscriptions_removes_every_roll_for_device():
    delete_for_device = AsyncMock(return_value=3)

    with patch(
        "service.subscriptionService.delete_result_device_subscriptions_for_device",
        new=delete_for_device,
    ):
        result = asyncio.run(
            delete_result_subscriptions("550e8400-e29b-41d4-a716-446655440000")
        )

    delete_for_device.assert_awaited_once_with(
        "550e8400-e29b-41d4-a716-446655440000"
    )
    assert result == {
        "msg": "Result notification subscriptions deleted",
        "deleted": 3,
    }
