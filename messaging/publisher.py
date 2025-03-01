import aio_pika
from fastapi import FastAPI
from config.redisConnection import redisConnection
from config.settings import QUEUE_NAME, REDIS_URL_KEY
from scrapers.serverChecker import check_url
from utils.logger import rabbitmq_logger


async def publish_message(app: FastAPI, rollNo: str):
    """Publishes a message (roll number) to the RabbitMQ queue."""

    try:
        if redisConnection.client:
            url = redisConnection.client.get(REDIS_URL_KEY)
            if url == "":
                return {
                    "status": "failure",
                    "message": "JNTUH SERVERS ARE DOWN!!",
                }
            elif not url:
                check_url()

        async with app.state.rabbitmq_connection.channel() as channel:
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)
            if queue.declaration_result.message_count > 600:
                rabbitmq_logger.warning("Server had execced the threshold level")
                return {
                    "status": "failure",
                    "message": "Server cannot handle the requests currently, please try again later",
                }

            await channel.default_exchange.publish(
                aio_pika.Message(body=rollNo.encode()),
                routing_key=QUEUE_NAME,
            )
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
