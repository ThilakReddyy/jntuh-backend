import asyncio
from collections.abc import Iterator

import aio_pika

from config.connection import prismaConnection
from config.redisConnection import redisConnection
from config.settings import (
    CLASS_RESULTS_PROCESSED_EXPIRY_TIME,
    CLASS_RESULTS_QUEUE_NAME,
    NOTIFICATIONS_REDIS_KEY,
    QUEUE_NAME,
    RABBITMQ_URL,
    RABBITMQ_ROLL_NUMBERS,
)
from database.operations import get_exam_codes_from_database, save_to_database
from scrapers.resultNotificationScraper import refresh_notifications
from scrapers.resultScraper import ResultScraper
from scrapers.serverChecker import check_url
from subscriptions.send_notification import send_push_notification_to_particular_user
from subscriptions.mobile_notification import notify_student_result_updated
from utils.logger import rabbitmq_logger, logger, scraping_logger
from utils.caching import invalidate_all_cache
from worker.health import worker_state


def get_class_prefixes(roll_number: str) -> tuple[str, str]:
    """Return the requested and paired class prefixes."""
    class_prefix = roll_number[:8]
    admission_type = class_prefix[4]

    if admission_type == "1":
        paired_year = str(int(class_prefix[:2]) + 1).zfill(2)
        paired_admission_type = "5"
    elif admission_type == "5":
        paired_year = str(int(class_prefix[:2]) - 1).zfill(2)
        paired_admission_type = "1"
    else:
        raise ValueError(
            f"Unsupported admission type in class roll number: {roll_number}"
        )

    paired_prefix = (
        paired_year
        + class_prefix[2:4]
        + paired_admission_type
        + class_prefix[5:8]
    )
    return class_prefix, paired_prefix


def iter_class_roll_numbers(roll_number: str) -> Iterator[str]:
    """Yield every roll number in the requested and paired class cohorts."""
    class_prefixes = get_class_prefixes(roll_number)

    for prefix in class_prefixes:
        for number in range(1, 100):
            yield f"{prefix}{number:02d}"
        for letter_code in range(ord("A"), ord("Z") + 1):
            letter = chr(letter_code)
            for number in range(10):
                yield f"{prefix}{letter}{number}"


async def process_class_results_message(message_body: str) -> None:
    """Scrape a class unless either paired cohort was processed in the last day."""
    rabbitmq_logger.info(f"Processing class results message: {message_body}")
    class_prefixes = get_class_prefixes(message_body)
    processed_keys = [
        f"class_results_processed:{prefix}" for prefix in class_prefixes
    ]

    if redisConnection.client and any(
        redisConnection.client.exists(key) for key in processed_keys
    ):
        rabbitmq_logger.info(
            f"Skipping class results for {message_body[:8]}; "
            "already processed within 24 hours"
        )
        return

    consecutive_empty_results = 0
    for student_roll_number in iter_class_roll_numbers(message_body):
        has_results = await process_message(student_roll_number)
        if has_results:
            consecutive_empty_results = 0
            continue

        consecutive_empty_results += 1
        if consecutive_empty_results >= 20:
            rabbitmq_logger.info(
                f"Stopping class results for {message_body[:8]} after "
                "20 consecutive roll numbers returned no results"
            )
            break

    if redisConnection.client:
        for key in processed_keys:
            redisConnection.client.set(
                key, "1", ex=CLASS_RESULTS_PROCESSED_EXPIRY_TIME
            )


# Define a function to process messages
async def process_message(message_body: str) -> bool:
    try:
        """
        Process the consumed message.
        Replace this logic with your custom processing code.
        """
        rabbitmq_logger.info(f"Processing message: {message_body}")

        url = check_url()
        if not url:
            rabbitmq_logger.warning("No url found, skipping processing...")
            return False

        # get exam codes present in database
        exam_codes = await get_exam_codes_from_database(message_body)
        exam_codes_rcrv = await get_exam_codes_from_database(message_body, True)

        # intializeing the scraper
        scraper = ResultScraper(message_body, exam_codes, exam_codes_rcrv, url)

        # running the scraper
        rabbitmq_logger.info(f"Started scraper for {message_body}")
        results = await scraper.run()

        # log if it fails to get the results

        if results is None:
            logger.warning(f"Failed to get results: {message_body}")
            return False

        logger.info(f"Results was successfully extracted: {message_body}")

        # Database save
        rabbitmq_logger.info(f"Saving results to database for {message_body}")
        inserted_count = await save_to_database(results)
        invalidate_all_cache(message_body)
        if inserted_count > 0:
            await send_push_notification_to_particular_user(message_body)
            try:
                await notify_student_result_updated(message_body)
            except Exception as error:
                logger.error(
                    f"Mobile student result notification failed for {message_body}: {error}"
                )
        return True

    except Exception as e:
        scraping_logger.error(f"Error while scarping results: {e}")
        return False

    """Consume messages from RabbitMQ and pass them to the processing function."""


async def _consume_default_queue(queue) -> None:
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                async with message.process():
                    body = message.body.decode()
                    # Remove the roll number from Redis after successful processing
                    if redisConnection.client:
                        redisConnection.client.srem(RABBITMQ_ROLL_NUMBERS, body)
                        rabbitmq_logger.info(
                            f"Removed roll number {body} from Redis."
                        )
                    else:
                        rabbitmq_logger.warning("Redis is not found")

                    if body == NOTIFICATIONS_REDIS_KEY:
                        await refresh_notifications()
                    else:
                        await process_message(body)

            except Exception as error:
                rabbitmq_logger.error(
                    f"Error processing message: {error},{message.body}"
                )
                if not message.processed:
                    await message.reject(requeue=False)


async def _consume_class_results_queue(queue) -> None:
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                async with message.process():
                    await process_class_results_message(message.body.decode())
            except Exception as error:
                rabbitmq_logger.error(
                    f"Error processing class results message: {error},{message.body}"
                )
                if not message.processed:
                    await message.reject(requeue=False)


async def consume_messages():
    try:
        # connection = app.state.rabbitmq_connection
        logger.info("Starting rabbitmq connection for consumer")

        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        worker_state.mark_ready()

        logger.info("Starting database connection for consumer")
        await prismaConnection.connect()

        logger.info("Starting redis connection for consumer")
        redisConnection.connect()

        async with connection:
            channel = await connection.channel()
            class_results_channel = await connection.channel()

            await channel.set_qos(prefetch_count=2)
            # Only one class batch may run at a time. Each batch also awaits
            # every individual roll number before starting the next one.
            await class_results_channel.set_qos(prefetch_count=1)

            queue = await channel.declare_queue(QUEUE_NAME, durable=True)
            class_results_queue = await class_results_channel.declare_queue(
                CLASS_RESULTS_QUEUE_NAME,
                durable=True,
            )
            rabbitmq_logger.info(f"Waiting for messages in queue: {QUEUE_NAME}")
            rabbitmq_logger.info(
                f"Waiting for messages in queue: {CLASS_RESULTS_QUEUE_NAME}"
            )

            await asyncio.gather(
                _consume_default_queue(queue),
                _consume_class_results_queue(class_results_queue),
            )

    except asyncio.CancelledError:
        rabbitmq_logger.info("Message consumption was cancelled.")
    except Exception as e:
        rabbitmq_logger.error(f"An error occurred: {e}")
    finally:
        worker_state.mark_not_ready()
        rabbitmq_logger.info("Shutting down gracefully...")
