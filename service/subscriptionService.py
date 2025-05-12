from database.models import PushSub
from database.operations import save_subscription_details


async def save_subscription(data: PushSub):
    try:
        await save_subscription_details(data)
        return {"msg": "Subscription saved"}
    except Exception:
        return {"error": "Subscription isn't saved.Some unknown error occured"}
