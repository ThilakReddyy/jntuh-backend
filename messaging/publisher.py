import aio_pika
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import QUEUE_NAME
from scrapers.serverChecker import check_valid_url_in_redis
from utils.logger import rabbitmq_logger


async def publish_message(app: FastAPI, rollNo: str):
    """Publishes a message (roll number) to the RabbitMQ queue."""

    try:
        if redisConnection.client:
            url = check_valid_url_in_redis()

            if url == ".":
                return {
                    "status": "failure",
                    "message": "JNTUH SERVERS ARE DOWN!!",
                }
            # Check if rollNo is already in Redis
            if redisConnection.client.sismember("rabbitmq_roll_numbers", rollNo):
                rabbitmq_logger.info(
                    f"Roll number {rollNo} already exists in queue. Skipping..."
                )
                return {
                    "status": "failure",
                    "message": "This roll number is already in the queue.",
                }

        async with app.state.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)

            message_count = queue.declaration_result.message_count
            unacked_count = (
                queue.declaration_result.consumer_count
            )  # Alternative way to track unacknowledged messages
            if message_count > 600 or unacked_count > 600:
                rabbitmq_logger.warning("Server had execced the threshold level")
                return {
                    "status": "failure",
                    "message": "Server cannot handle the requests currently, please try again later",
                }

            await channel.default_exchange.publish(
                aio_pika.Message(body=rollNo.encode()),
                routing_key=QUEUE_NAME,
            )

            if redisConnection.client:
                redisConnection.client.sadd("rabbitmq_roll_numbers", rollNo)
        return {
            "status": "success",
            "message": "Your roll number has been queued.",
        }
    except Exception as e:
        rabbitmq_logger.error(f"Unknown Exception while publishing: {e}")
        return {
            "status": "failure",
            "message": "Unknown Exception has occured!!",
        }
