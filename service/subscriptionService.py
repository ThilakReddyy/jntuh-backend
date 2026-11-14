from database.models import APNSDeviceRegistrationPayload, PushSub, ResultDeviceSubscriptionPayload
from database.operations import (
    delete_apns_device_for_device,
    delete_result_device_subscriptions_for_device,
    save_apns_device,
    save_result_device_subscription,
    save_subscription_details,
)
from utils.telemetry import log_failure, trace_function


@trace_function(log_completion=True)
async def save_subscription(data: PushSub):
    try:
        await save_subscription_details(data)
        return {"msg": "Subscription saved"}
    except Exception as error:
        log_failure("subscriptions.save", error)
        return {"error": "Subscription isn't saved.Some unknown error occured"}


@trace_function(log_completion=True)
async def save_result_subscription(data: ResultDeviceSubscriptionPayload):
    await save_result_device_subscription(data)
    return {"msg": "Result notification subscription saved"}


@trace_function(log_completion=True)
async def delete_result_subscriptions(device_id: str):
    deleted = await delete_result_device_subscriptions_for_device(device_id)
    return {
        "msg": "Result notification subscriptions deleted",
        "deleted": deleted,
    }


@trace_function(log_completion=True)
async def register_apns_device(data: APNSDeviceRegistrationPayload):
    await save_apns_device(data)
    return {"msg": "APNs device registered"}


@trace_function(log_completion=True)
async def unregister_apns_device(device_id: str):
    deleted = await delete_apns_device_for_device(device_id)
    return {"msg": "APNs device unregistered", "deleted": deleted}
