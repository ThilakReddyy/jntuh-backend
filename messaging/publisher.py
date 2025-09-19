import aio_pika
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from config.redisConnection import redisConnection
from config.settings import (
    NOTIFICATIONS_REDIS_KEY,
    QUEUE_NAME,
    RABBITMQ_MAX_MESSAGES,
    RABBITMQ_ROLL_NUMBERS,
)
from scrapers.serverChecker import check_valid_url_in_redis
from utils.logger import rabbitmq_logger


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
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content={
                        "status": "failure",
                        "message": "JNTUH SERVERS ARE DOWN!!",
                    },
                )

            # Check if rollNo is already in Redis
            if redisConnection.client.sismember(RABBITMQ_ROLL_NUMBERS, rollNo):
                rabbitmq_logger.info(
                    f"Roll number {rollNo} already exists in queue. Skipping..."
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "status": "failure",
                        "message": "This roll number is already in the queue.",
                    },
                )

        async with app.state.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)

            message_count = queue.declaration_result.message_count
            if message_count > RABBITMQ_MAX_MESSAGES:
                rabbitmq_logger.warning("Server had execced the threshold level")
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content={
                        "status": "failure",
                        "message": "Server cannot handle the requests currently, please try again later",
                    },
                )

            await channel.default_exchange.publish(
                aio_pika.Message(body=rollNo.encode()),
                routing_key=QUEUE_NAME,
            )

        if rollNo == NOTIFICATIONS_REDIS_KEY:
            return {"status": "success", "message": "Notifications are been fetched"}

        if redisConnection.client:
            if not redisConnection.client.exists(RABBITMQ_ROLL_NUMBERS):
                redisConnection.client.sadd(RABBITMQ_ROLL_NUMBERS, rollNo.encode())
                redisConnection.client.expire(RABBITMQ_ROLL_NUMBERS, 3600)
            else:
                redisConnection.client.sadd(RABBITMQ_ROLL_NUMBERS, rollNo.encode())
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
