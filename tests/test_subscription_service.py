import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from database.models import APNSDeviceRegistrationPayload, NotificationPreferencePayload
from service.subscriptionService import (
    delete_notification_preferences,
    delete_result_subscriptions,
    get_notification_preferences,
    register_apns_device,
    save_notification_preferences,
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


def test_save_notification_preferences_returns_resolved_topics():
    save_preference = AsyncMock()
    payload = NotificationPreferencePayload(
        deviceId="550e8400-e29b-41d4-a716-446655440000",
        degrees=["btech"],
        regulations=["R18"],
    )

    with patch(
        "service.subscriptionService.save_notification_preference",
        new=save_preference,
    ):
        result = asyncio.run(save_notification_preferences(payload))

    save_preference.assert_awaited_once_with(payload)
    assert result == {
        "msg": "Notification preferences saved",
        "topics": ["result-updates-btech-r18"],
    }


def test_get_notification_preferences_defaults_to_global_topic_when_absent():
    get_preference = AsyncMock(return_value=None)
    device_id = "550e8400-e29b-41d4-a716-446655440000"

    with patch(
        "service.subscriptionService.get_notification_preference",
        new=get_preference,
    ):
        result = asyncio.run(get_notification_preferences(device_id))

    assert result == {
        "deviceId": device_id,
        "degrees": [],
        "regulations": [],
        "topics": ["result-updates"],
    }


def test_get_notification_preferences_resolves_saved_topics():
    stored = SimpleNamespace(
        deviceId="550e8400-e29b-41d4-a716-446655440000",
        degrees=["btech", "mtech"],
        regulations=["r18"],
    )
    get_preference = AsyncMock(return_value=stored)

    with patch(
        "service.subscriptionService.get_notification_preference",
        new=get_preference,
    ):
        result = asyncio.run(
            get_notification_preferences("550e8400-e29b-41d4-a716-446655440000")
        )

    assert result == {
        "deviceId": "550e8400-e29b-41d4-a716-446655440000",
        "degrees": ["btech", "mtech"],
        "regulations": ["r18"],
        "topics": ["result-updates-btech-r18", "result-updates-mtech-r18"],
    }


def test_delete_notification_preferences_resets_to_global_topic():
    delete_preference = AsyncMock(return_value=1)
    device_id = "550e8400-e29b-41d4-a716-446655440000"

    with patch(
        "service.subscriptionService.delete_notification_preference_for_device",
        new=delete_preference,
    ):
        result = asyncio.run(delete_notification_preferences(device_id))

    delete_preference.assert_awaited_once_with(device_id)
    assert result == {
        "msg": "Notification preferences reset",
        "deleted": 1,
        "topics": ["result-updates"],
    }


def test_notification_preference_payload_rejects_unknown_degree():
    with pytest.raises(ValidationError):
        NotificationPreferencePayload(
            deviceId="550e8400-e29b-41d4-a716-446655440000",
            degrees=["cse"],
        )


def test_notification_preference_payload_normalizes_regulation_case():
    payload = NotificationPreferencePayload(
        deviceId="550e8400-e29b-41d4-a716-446655440000",
        regulations=["r18"],
    )
    assert payload.regulations == ["R18"]


def test_notification_preference_payload_rejects_free_text_regulation():
    with pytest.raises(ValidationError):
        NotificationPreferencePayload(
            deviceId="550e8400-e29b-41d4-a716-446655440000",
            regulations=["Set-1"],
        )


def test_notification_preference_payload_rejects_non_uuid_device_id():
    with pytest.raises(ValidationError):
        NotificationPreferencePayload(deviceId="not-a-uuid")
