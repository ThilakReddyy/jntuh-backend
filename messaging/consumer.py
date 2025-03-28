import asyncio
import aio_pika

from config.connection import prismaConnection
from config.redisConnection import redisConnection
from config.settings import NOTIFICATIONS_REDIS_KEY, QUEUE_NAME, RABBITMQ_URL
from database.operations import get_exam_codes_from_database, save_to_database
from scrapers.resultNotificationScraper import get_notifications
from scrapers.resultScraper import ResultScraper
from scrapers.serverChecker import check_url
from utils.logger import rabbitmq_logger, logger, scraping_logger


# Define a function to process messages
async def process_message(message_body: str):
    try:
        """
        Process the consumed message.
        Replace this logic with your custom processing code.
        """
        rabbitmq_logger.info(f"Processing message: {message_body}")

        # Remove the roll number from Redis after successful processing
        if redisConnection.client:
            redisConnection.client.srem("rabbitmq_roll_numbers", message_body)
            rabbitmq_logger.info(f"Removed roll number {message_body} from Redis.")

        url = check_url()
        if not url:
            rabbitmq_logger.warning("No url found, skipping processing...")
            return

        exam_codes = await get_exam_codes_from_database(message_body)
        scraper = ResultScraper(message_body, exam_codes, url)
        rabbitmq_logger.info(f"Started scraper for {message_body}")
        results = await scraper.run()
        if results is None:
            logger.warning(f"Failed to get results: {message_body}")
            return
        logger.info(f"Results was successfully extracted: {message_body}")

        # Database save
        rabbitmq_logger.info(f"Saving results to database for {message_body}")
        await save_to_database(results)

    except Exception as e:
        scraping_logger.error(f"Error while scarping results: {e}")

    """Consume messages from RabbitMQ and pass them to the processing function."""


async def consume_messages():
    try:
        # connection = app.state.rabbitmq_connection
        logger.info("Starting rabbitmq connection for consumer")

        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        logger.info("Starting database connection for consumer")
        await prismaConnection.connect()

        logger.info("Starting redis connection for consumer")
        redisConnection.connect()

        async with connection:
            channel = await connection.channel()

            await channel.set_qos(prefetch_count=2)  # ADD THIS LINE

            # Declare the queue
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)
            rabbitmq_logger.info(f"Waiting for messages in queue: {QUEUE_NAME}")

            # Create an asynchronous iterator for the queue
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    try:
                        async with message.process():
                            body = message.body.decode()
                            if body == NOTIFICATIONS_REDIS_KEY:
                                await get_notifications()
                            else:
                                await process_message(body)

                    except Exception as e:
                        rabbitmq_logger.error(
                            f"Error processing message: {e},{message.body}"
                        )
                        # Optionally, you can reject or requeue the message here
                        await message.reject(requeue=False)

    except asyncio.CancelledError:
        rabbitmq_logger.info("Message consumption was cancelled.")
    except Exception as e:
        rabbitmq_logger.error(f"An error occurred: {e}")
    finally:
        rabbitmq_logger.info("Shutting down gracefully...")
