import asyncio
import json
from pywebpush import WebPushException, webpush

from config.settings import VAPID_PRIVATE_KEY
from database.operations import get_all_subscriptions, get_subscription_roll_number
from utils.logger import logger
from utils.telemetry import log_failure, trace_function


@trace_function
def send_push_notification(subscription_info, title, body):
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(
                {
                    "title": title,
                    "body": body,
                    "url": "https://jntuhconnect.dhethi.com/academicresult",
                }
            ),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:admin@dhethi.com"},
        )
    except WebPushException as ex:
        log_failure("notifications.webpush.send", ex)


@trace_function
async def send_push_notification_to_particular_user(roll_number: str):
    record = await get_subscription_roll_number(roll_number)
    if record and record.subscription:
        sub_obj = json.loads(record.subscription)
        send_push_notification(
            sub_obj, "✅ Done!", f"Result for {roll_number} is ready."
        )
        logger.info(
            f"msg: Result for {roll_number} is ready and push notification is been sent"
        )


@trace_function
async def broadcast_all(title: str):
    all_subs = await get_all_subscriptions()

    @trace_function
    async def send_async():
        await asyncio.gather(
            *[
                asyncio.to_thread(
                    send_push_notification,
                    json.loads(record.subscription or ""),
                    f"📢 JNTUH Results Released! {title}",
                    "Tap to check your result now on jntuhconnect.dhethi.com",
                )
                for record in all_subs
            ]
        )

    await send_async()

    logger.info("msg :Broadcast sent to all subscribed users")
