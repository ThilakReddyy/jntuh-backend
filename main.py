import aio_pika
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio


from api.routes import create_routes
from config.redisConnection import redisConnection
from config.connection import prismaConnection
from config.settings import RABBITMQ_URL
from messaging.consumer import consume_messages
from utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the lifespan of the application, ensuring RabbitMQ connection is opened and closed properly."""
    try:
        logger.info("Starting FastAPI & RabbitMQ Consumer...")
        app.state.rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
        await prismaConnection.connect()
        redisConnection.connect()

        consumer_task = asyncio.create_task(consume_messages(app))

        yield

        logger.info("Shutting down RabbitMQ Consumer...")
        consumer_task.cancel()
    finally:
        await app.state.rabbitmq_connection.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Use specific domains in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

routes = create_routes(app)
app.include_router(routes)
