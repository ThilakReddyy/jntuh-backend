from config.redisConnection import redisConnection


def invalidate_all_cache(roll_number: str):
    roll_credits_checker_key = f"{roll_number}RequiredCredits"
    roll_backlogs_key = f"{roll_number}Backlogs"
    roll_all_key = f"{roll_number}ALL"
    roll_results_key = f"{roll_number}Results"

    if redisConnection.client:
        redisConnection.client.delete(roll_credits_checker_key)
        redisConnection.client.delete(roll_backlogs_key)
        redisConnection.client.delete(roll_all_key)
        redisConnection.client.delete(roll_results_key)
