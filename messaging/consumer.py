import asyncio
from fastapi.applications import FastAPI

from config.settings import NOTIFICATIONS_REDIS_KEY, QUEUE_NAME
from database.operations import save_to_database
from scrapers.resultNotificationScraper import get_notifications
from scrapers.resultScraper import ResultScraper
from utils.logger import rabbitmq_logger, logger


# Define a function to process messages
async def process_message(message_body: str):
    """
    Process the consumed message.
    Replace this logic with your custom processing code.
    """
    rabbitmq_logger.info(f"Processing message: {message_body}")
    scraper = ResultScraper(message_body, url="http://202.63.105.184/resultAction")
    # scraper = ResultScraper(message_body)
    results = await scraper.run()
    if results is None:
        logger.warning(f"Failed to get results: {message_body}")
        return
    logger.info(f"Results was successfully extracted: {message_body}")
    await save_to_database(results)


async def consume_messages(app: FastAPI):
    """Consume messages from RabbitMQ and pass them to the processing function."""
    try:
        connection = app.state.rabbitmq_connection

        async with connection:
            channel = await connection.channel()

            # Declare the queue
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)
            rabbitmq_logger.info(f"Waiting for messages in queue: {QUEUE_NAME}")

            # Create an asynchronous iterator for the queue
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    try:
                        async with message.process():
                            if message.body.decode() == NOTIFICATIONS_REDIS_KEY:
                                get_notifications()
                            else:
                                await process_message(message.body.decode())
                    except Exception as e:
                        rabbitmq_logger.error(f"Error processing message: {e}")
                        # Optionally, you can reject or requeue the message here
                        # await message.reject(requeue=True)

    except asyncio.CancelledError:
        rabbitmq_logger.info("Message consumption was cancelled.")
    except Exception as e:
        rabbitmq_logger.error(f"An error occurred: {e}")
    finally:
        rabbitmq_logger.info("Shutting down gracefully...")
