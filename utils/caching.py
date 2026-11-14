from config.redisConnection import redisConnection
from prometheus_client import Counter
from utils.telemetry import operation, trace_function


CACHE_READS = Counter(
    "result_cache_reads_total", "Core result-view cache outcomes.", ("view", "outcome")
)


@trace_function
def get_cached_result(key: str, view: str):
    with operation("redis.get", attributes={"cache.view": view}) as span:
        if not redisConnection.client:
            CACHE_READS.labels(view, "unavailable").inc()
            return None
        try:
            value = redisConnection.client.get(key)
        except Exception:
            CACHE_READS.labels(view, "error").inc()
            raise
        outcome = "hit" if value else "miss"
        CACHE_READS.labels(view, outcome).inc()
        span.set_attribute("cache.outcome", outcome)
        return value if value else None


@trace_function
def invalidate_all_cache(roll_number: str):
    roll_credits_checker_key = f"{roll_number}RequiredCredits"
    roll_backlogs_key = f"{roll_number}Backlogs"
    roll_all_key = f"{roll_number}ALL"
    roll_results_key = f"{roll_number}Results"

    if redisConnection.client:
        with operation("redis.invalidate_results"):
            redisConnection.client.delete(roll_credits_checker_key)
            redisConnection.client.delete(roll_backlogs_key)
            redisConnection.client.delete(roll_all_key)
            redisConnection.client.delete(roll_results_key)
