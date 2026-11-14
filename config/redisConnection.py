import redis
from config.settings import REDIS_URL
from utils.logger import redis_logger
from utils.observability import CACHE, operation


class RedisConnection:
    def __init__(self):
        self.redis_url = REDIS_URL
        self.client = None

    def connect(self):
        if self.redis_url:
            self.client = redis.Redis.from_url(self.redis_url, socket_connect_timeout=3, socket_timeout=3)
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
    if not redisConnection.client:
        CACHE.labels("unavailable").inc()
        return None
    with operation("redis", "cache_get"):
        try:
            cached_data = redisConnection.client.get(key)
        except Exception:
            CACHE.labels("error").inc()
            raise
        CACHE.labels("hit" if cached_data is not None else "miss").inc()
        return cached_data
