from database.models import PushSub, ResultDeviceSubscriptionPayload
from database.operations import save_result_device_subscription, save_subscription_details


async def save_subscription(data: PushSub):
    try:
        await save_subscription_details(data)
        return {"msg": "Subscription saved"}
    except Exception:
        return {"error": "Subscription isn't saved.Some unknown error occured"}


async def save_result_subscription(data: ResultDeviceSubscriptionPayload):
    await save_result_device_subscription(data)
    return {"msg": "Result notification subscription saved"}
