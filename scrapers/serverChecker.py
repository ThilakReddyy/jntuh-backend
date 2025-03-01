import requests
from config.settings import EXPIRY_TIME, FIVE_MINUTE_EXPIRY, REDIS_URL_KEY
from utils.logger import scraping_logger
from config.redisConnection import redisConnection


def check_url():
    urls = [
        "http://202.63.105.184/results/resultAction",
        "https://results.jntuh.ac.in/results/resultAction",
    ]

    # Check Redis cache first
    if redisConnection.client:
        cached_url = redisConnection.client.get(REDIS_URL_KEY)
        if cached_url:
            cached_url = (
                cached_url.decode("utf-8")
                if isinstance(cached_url, bytes)
                else cached_url
            )
            if cached_url:
                print(str(cached_url), cached_url)
                return str(cached_url)

    # Try each URL
    for url in urls:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code in {200, 201}:
                scraping_logger.info(f"The URL {url} is working")

                # Cache the result in Redis
                if redisConnection.client:
                    redisConnection.client.set(REDIS_URL_KEY, url, ex=EXPIRY_TIME)

                return url  # Return the first working URL
        except requests.exceptions.Timeout:
            scraping_logger.warning(f"The URL {url} timed out")
        except requests.exceptions.RequestException:
            scraping_logger.warning(f"The URL {url} is not working")

    if redisConnection.client:
        redisConnection.client.set(REDIS_URL_KEY, "", ex=FIVE_MINUTE_EXPIRY)

    return None

