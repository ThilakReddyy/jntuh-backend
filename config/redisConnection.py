import redis
from config.settings import REDIS_URL
from utils.logger import redis_logger


class RedisConnection:
    def __init__(self):
        self.redis_url = REDIS_URL
        self.client = None

    def connect(self):
        if self.redis_url:
            self.client = redis.Redis.from_url(self.redis_url)
            try:
                self.client.ping()
                redis_logger.info("Redis Connected!!")
            except redis.ConnectionError:
                redis_logger.error("Failed to connect to Redis")

    def disconnect(self):
        if self.client:
            self.client.close()
            redis_logger.info("Redis Disconnected!!")


redisConnection = RedisConnection()


def getRedisKeyValue(key):
    if redisConnection.client:
        cached_data = redisConnection.client.get(key)
        if cached_data:
            redis_logger.info(f"Cache hit for {key}")
            return cached_data  # pyright: ignore
    return None
