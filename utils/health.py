import asyncio
from fastapi.responses import JSONResponse
from config.connection import prismaConnection
from config.redisConnection import redisConnection


async def readiness(app):
    async def database():
        await prismaConnection.prisma.query_raw("SELECT 1")

    async def redis():
        if redisConnection.client is None:
            raise RuntimeError("Redis not initialized")
        await asyncio.to_thread(redisConnection.client.ping)

    async def rabbitmq():
        connection = getattr(app.state, "rabbitmq_connection", None)
        if connection is None or connection.is_closed:
            raise RuntimeError("RabbitMQ disconnected")
        async with connection.channel():
            pass

    async def check(fn):
        try:
            await asyncio.wait_for(fn(), timeout=4)
            return "up"
        except Exception:
            return "down"

    results = await asyncio.gather(*(check(fn) for fn in (database, redis, rabbitmq)))
    checks = dict(zip(("postgres", "redis", "rabbitmq"), results))
    healthy = all(value == "up" for value in results)
    return JSONResponse(status_code=200 if healthy else 503,
                        content={"status": "ready" if healthy else "not_ready", "checks": checks})
