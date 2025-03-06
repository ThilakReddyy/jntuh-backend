import aio_pika
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from fastapi.openapi.utils import get_openapi


from api.routes import create_routes
from config.redisConnection import redisConnection
from config.connection import prismaConnection
from config.settings import RABBITMQ_URL
from messaging.consumer import consume_messages
from utils.logger import logger
from prometheus_fastapi_instrumentator import Instrumentator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the lifespan of the application, ensuring RabbitMQ connection is opened and closed properly."""
    try:
        logger.info("Starting FastAPI & RabbitMQ Consumer...")
        app.state.rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
        await prismaConnection.connect()
        redisConnection.connect()

        # consumer_task = asyncio.create_task(consume_messages(app))

        yield

        logger.info("Shutting down RabbitMQ Consumer...")
        # consumer_task.cancel()
    finally:
        await app.state.rabbitmq_connection.close()


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
            "url": "https://jntuhresults.vercel.app/_next/image?url=%2Fjntuhresults_md.png&w=256&q=75"
        }
    return app.openapi_schema


app = FastAPI(lifespan=lifespan)

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Use specific domains in production)
    allow_credentials=True,
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
    client_ip = request.client.host  # Capture the client's IP
    logger.info(f"Request from {client_ip}: {request.method} {request.url.path}")

    # Process the request and continue
    response = await call_next(request)
    return response


routes = create_routes(app)
app.include_router(routes)
