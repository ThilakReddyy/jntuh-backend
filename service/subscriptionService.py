from database.models import (
    APNSDeviceRegistrationPayload,
    NotificationPreferencePayload,
    PushSub,
    ResultDeviceSubscriptionPayload,
)
from database.operations import (
    delete_apns_device_for_device,
    delete_notification_preference_for_device,
    delete_result_device_subscriptions_for_device,
    get_notification_preference,
    save_apns_device,
    save_notification_preference,
    save_result_device_subscription,
    save_subscription_details,
)
from subscriptions.topics import FCM_RESULTS_TOPIC, topics_for_preference


async def save_subscription(data: PushSub):
    try:
        await save_subscription_details(data)
        return {"msg": "Subscription saved"}
    except Exception:
        return {"error": "Subscription isn't saved.Some unknown error occured"}


async def save_result_subscription(data: ResultDeviceSubscriptionPayload):
    await save_result_device_subscription(data)
    return {"msg": "Result notification subscription saved"}


async def delete_result_subscriptions(device_id: str):
    deleted = await delete_result_device_subscriptions_for_device(device_id)
    return {
        "msg": "Result notification subscriptions deleted",
        "deleted": deleted,
    }


async def register_apns_device(data: APNSDeviceRegistrationPayload):
    await save_apns_device(data)
    return {"msg": "APNs device registered"}


async def unregister_apns_device(device_id: str):
    deleted = await delete_apns_device_for_device(device_id)
    return {"msg": "APNs device unregistered", "deleted": deleted}


def _resolved_topics(degrees: list[str], regulations: list[str]) -> list[str]:
    return topics_for_preference(
        [degree.lower() for degree in degrees],
        [regulation.lower() for regulation in regulations],
    )


async def save_notification_preferences(data: NotificationPreferencePayload):
    await save_notification_preference(data)
    return {
        "msg": "Notification preferences saved",
        "topics": _resolved_topics(data.degrees, data.regulations),
    }


async def get_notification_preferences(device_id: str):
    preference = await get_notification_preference(device_id)
    if preference is None:
        return {
            "deviceId": device_id,
            "degrees": [],
            "regulations": [],
            "topics": [FCM_RESULTS_TOPIC],
        }
    return {
        "deviceId": preference.deviceId,
        "degrees": preference.degrees,
        "regulations": preference.regulations,
        "topics": _resolved_topics(preference.degrees, preference.regulations),
    }


async def delete_notification_preferences(device_id: str):
    deleted = await delete_notification_preference_for_device(device_id)
    return {
        "msg": "Notification preferences reset",
        "deleted": deleted,
        "topics": [FCM_RESULTS_TOPIC],
    }
