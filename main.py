import aio_pika
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi_mcp import FastApiMCP
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.routes import create_routes
from config.apiHeaderGuard import ApiKeyHeaderMiddleware
from config.rateLimiter import ExemptingSlowAPIMiddleware, limiter
from config.redisConnection import redisConnection
from config.connection import prismaConnection
from config.settings import RABBITMQ_URL
from utils.logger import logger
from utils.mcpMetrics import instrument_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the lifespan of the application, ensuring RabbitMQ connection is opened and closed properly."""
    try:
        logger.info("Starting FastAPI & RabbitMQ Consumer...")
        app.state.rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
        await prismaConnection.connect()
        redisConnection.connect()

        yield

        logger.info("Shutting down...")
    finally:
        if hasattr(app.state, "rabbitmq_connection"):
            await app.state.rabbitmq_connection.close()

        # Disconnect Prisma
        await prismaConnection.disconnect()

        # Close Redis
        if hasattr(app.state, "redis"):
            await app.state.redis.close()


def custom_openapi():
    """Generate and cache a custom OpenAPI schema for the FastAPI application."""
    if not app.openapi_schema:
        app.openapi_schema = get_openapi(
            title="JNTUH RESULTS API",
            version="0.1.0",
            summary="API for retrieving student results and academic information",
            description="The JNTUH Results API provides access to student records, including academic results, "
            "backlog details, and overall performance summaries. This API is designed to streamline "
            "access to university result data in a structured format.",
            routes=app.routes,
        )
        app.openapi_schema["info"]["x-logo"] = {
            "url": "https://jntuhconnect.dhethi.com/_next/image?url=%2Fjntuhresults_md.png&w=256&q=75"
        }
    return app.openapi_schema


app = FastAPI(lifespan=lifespan)

app.openapi = custom_openapi

# Rate limiting. Added before CORSMiddleware so CORS ends up outermost and
# 429 responses from the limiter still carry the CORS headers the browser needs.
# ExemptingSlowAPIMiddleware skips paths under EXEMPT_PATH_PREFIXES (e.g. /mcp).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(ExemptingSlowAPIMiddleware)

# Require the X-Api-Key header on every API route (exempt: /mcp, /metrics,
# docs, static pages — see config/apiHeaderGuard.py). Added after slowapi so
# rejected requests never touch the rate limiter, and before CORS so 403s
# still carry the CORS headers the browser needs.
app.add_middleware(ApiKeyHeaderMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://jntuhresults.dhethi.com",
        "https://jntuhconnect.dhethi.com",
        "https://dhethi.com",
        "http://localhost:3000",
        "http://localhost:3001",
    ],  # Allows all origins (Use specific domains in production)
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# Initialize Prometheus instrumentator
instrumentator = Instrumentator()

# Automatically instrument the FastAPI app to expose Prometheus metrics
# Exposing metrics at /metrics
instrumentator.instrument(app).expose(app, include_in_schema=False)


@app.middleware("http")
async def log_request(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000
    logger.info(
        f"{request.client.host} {request.method} {request.url.path} "
        f"→ {response.status_code} [{duration:.2f} ms]"
    )

    return response


routes = create_routes(app)
app.include_router(routes)

mcp = FastApiMCP(
    app,
    name="JNTUH Results MCP",
    description=(
        "MCP tools for querying JNTUH student academic data: full attempt history "
        "(getAllResult) vs the consolidated best-attempt mark sheet "
        "(getAcademicResult), backlogs, credits-vs-required-credits, two-student "
        "result contrast, class-wide results, grace-marks eligibility, and "
        "result notifications. Read-only — destructive endpoints are intentionally "
        "not exposed."
    ),
    include_operations=[
        "get_all_result",
        "get_academic_result",
        "get_backlogs",
        "get_credits_checker",
        "get_result_contrast",
        "check_grace_marks_eligibility",
        "get_class_results",
        "get_notifications",
        "get_latest_notifications",
    ],
)
mcp.mount_http()
instrument_mcp(mcp)
