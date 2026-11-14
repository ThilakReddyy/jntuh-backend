import aio_pika
from opentelemetry import propagate
from opentelemetry.trace import SpanKind
from utils.observability import operation
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from config.redisConnection import redisConnection
from config.settings import (
    CLASS_RESULTS_QUEUE_MAX_MESSAGES,
    CLASS_RESULTS_QUEUE_NAME,
    NOTIFICATIONS_REDIS_KEY,
    QUEUE_NAME,
    RABBITMQ_MAX_MESSAGES,
)
from scrapers.serverChecker import check_valid_url_in_redis
from utils.logger import rabbitmq_logger


async def publish_class_results_message(app: FastAPI, roll_number: str) -> bool:
    """Publish a class-results request to its dedicated RabbitMQ queue."""
    async with app.state.rabbitmq_connection.channel() as channel:
        queue = await channel.declare_queue(CLASS_RESULTS_QUEUE_NAME, durable=True)
        message_count = queue.declaration_result.message_count
        if message_count >= CLASS_RESULTS_QUEUE_MAX_MESSAGES:
            rabbitmq_logger.warning(
                f"Skipping {roll_number}; queue {CLASS_RESULTS_QUEUE_NAME} "
                f"already has {message_count} messages"
            )
            return False

        await _publish(channel.default_exchange, roll_number, CLASS_RESULTS_QUEUE_NAME)
    rabbitmq_logger.info(
        f"Published {roll_number} to queue: {CLASS_RESULTS_QUEUE_NAME}"
    )
    return True


async def publish_message(
    app: FastAPI,
    rollNo: str,
):
    """Publishes a message (roll number) to the RabbitMQ queue."""

    try:
        if redisConnection.client:
            url = check_valid_url_in_redis()

            if url == ".":
                return JSONResponse(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    content={
                        "status": "failure",
                        "message": "JNTUH SERVERS ARE DOWN!!",
                    },
                )

        async with app.state.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)

            message_count = queue.declaration_result.message_count
            if message_count > RABBITMQ_MAX_MESSAGES:
                rabbitmq_logger.warning("Server had execced the threshold level")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "status": "failure",
                        "message": "Server cannot handle the requests currently, please try again later",
                    },
                )

            await _publish(channel.default_exchange, rollNo, QUEUE_NAME)

        if rollNo == NOTIFICATIONS_REDIS_KEY:
            return {"status": "success", "message": "Notifications are been fetched"}

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "success",
                "message": "Your roll number has been queued.",
            },
        )

    except Exception as e:
        rabbitmq_logger.error(f"Unknown Exception while publishing: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failure",
                "message": "Unknown Exception has occurred!!",
            },
        )


async def _publish(exchange, body, queue):
    with operation("rabbitmq", "publish", kind=SpanKind.PRODUCER):
        headers = {}
        propagate.inject(headers)
        await exchange.publish(
            aio_pika.Message(body=body.encode(), headers=headers,
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=queue,
        )
