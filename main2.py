from messaging.consumer import consume_messages
from config.settings import WORKER_HEALTH_PORT
from worker.health import start_worker_health_server
import asyncio


async def main():
    start_worker_health_server(WORKER_HEALTH_PORT)
    await consume_messages()


asyncio.run(main())

