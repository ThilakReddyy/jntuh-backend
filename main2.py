import asyncio

from prometheus_client import start_http_server

from config.observability import (
    WORKER_METRICS_ENABLED, WORKER_METRICS_HOST, WORKER_METRICS_PORT,
)
from utils.logger import logger
from utils.telemetry import configure_telemetry, shutdown_telemetry

configure_telemetry("worker")

from messaging.consumer import consume_messages


async def main():
    metrics_server = None
    try:
        if WORKER_METRICS_ENABLED:
            try:
                metrics_server, _ = start_http_server(
                    WORKER_METRICS_PORT, addr=WORKER_METRICS_HOST,
                )
            except OSError:
                logger.exception("Worker metrics listener could not start")
        await consume_messages()
    finally:
        if metrics_server is not None:
            await asyncio.to_thread(metrics_server.shutdown)
            metrics_server.server_close()
        await asyncio.to_thread(shutdown_telemetry)


if __name__ == "__main__":
    asyncio.run(main())

