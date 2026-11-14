import requests
from config.settings import EXPIRY_TIME, FIVE_MINUTE_EXPIRY, REDIS_URL_KEY
from utils.logger import scraping_logger
from config.redisConnection import redisConnection


def check_url():
    urls = [
        "http://results.jntuh.ac.in/results/resultAction?degree=btech&examCode=1323&etype=r16&result=null&grad=null&type=intgrade&htno=18E51A0479",
        "http://202.63.105.184/results/resultAction?degree=btech&examCode=1323&etype=r16&result=null&grad=null&type=intgrade&htno=18E51A0479",
    ]

    # Check Redis cache first
    url = check_valid_url_in_redis()

    if url is not None and url != ".":
        return url

    # Try each URL
    for url in urls:
        optimized_url = url.split("?")[0]

        try:
            response = requests.get(url, timeout=5)
            if response.status_code in {200, 201}:
                scraping_logger.info(f"The URL {optimized_url} is working")

                # Cache the result in Redis
                if redisConnection.client:
                    redisConnection.client.set(
                        REDIS_URL_KEY, optimized_url, ex=EXPIRY_TIME
                    )

                return optimized_url  # Return the first working URL
        except requests.exceptions.Timeout:
            scraping_logger.warning(f"The URL {optimized_url} timed out")
        except requests.exceptions.RequestException:
            scraping_logger.warning(f"The URL {url} is not working")
        except Exception:
            scraping_logger.warning(f"The URL {url} is given an unexpected error")

    if redisConnection.client:
        redisConnection.client.set(REDIS_URL_KEY, ".", ex=FIVE_MINUTE_EXPIRY)

    return None


def check_valid_url_in_redis():
    if redisConnection.client:
        cached_url = redisConnection.client.get(REDIS_URL_KEY)
        if cached_url is not None:
            cached_url = (
                cached_url.decode("utf-8")
                if isinstance(cached_url, bytes)
                else cached_url
            )
            if cached_url:
                return str(cached_url)
