import asyncio
import os
import time

from prometheus_client import start_http_server
from utils.observability import WORKER_HEARTBEAT, setup_telemetry, shutdown_telemetry
from messaging.consumer import consume_messages


async def heartbeat():
    while True:
        WORKER_HEARTBEAT.set(time.time())
        await asyncio.sleep(5)


async def main():
    setup_telemetry(os.getenv("OTEL_SERVICE_NAME", "jntuh-worker"))
    start_http_server(int(os.getenv("WORKER_METRICS_PORT", "8001")))
    task = asyncio.create_task(heartbeat())
    try:
        await consume_messages()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        shutdown_telemetry()


if __name__ == "__main__":
    asyncio.run(main())
