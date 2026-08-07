import asyncio
from unittest.mock import AsyncMock, patch

from database.models import APNSDeviceRegistrationPayload
from service.subscriptionService import (
    delete_result_subscriptions,
    register_apns_device,
    unregister_apns_device,
)


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


def test_register_apns_device_is_idempotent_service_call():
    save_device = AsyncMock()
    payload = APNSDeviceRegistrationPayload(
        deviceId="550e8400-e29b-41d4-a716-446655440000",
        deviceToken="ab" * 32,
        environment="sandbox",
    )

    with patch(
        "service.subscriptionService.save_apns_device",
        new=save_device,
    ):
        result = asyncio.run(register_apns_device(payload))

    save_device.assert_awaited_once_with(payload)
    assert result == {"msg": "APNs device registered"}


def test_unregister_apns_device_uses_stable_device_id():
    delete_device = AsyncMock(return_value=1)
    device_id = "550e8400-e29b-41d4-a716-446655440000"

    with patch(
        "service.subscriptionService.delete_apns_device_for_device",
        new=delete_device,
    ):
        result = asyncio.run(unregister_apns_device(device_id))

    delete_device.assert_awaited_once_with(device_id)
    assert result == {"msg": "APNs device unregistered", "deleted": 1}
