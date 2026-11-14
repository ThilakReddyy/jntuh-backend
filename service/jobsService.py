import asyncio
import json

from config.redisConnection import redisConnection
from database.jobOperations import deactivate_stale_jobs, get_jobs, save_jobs
from scrapers.jobScraper import scrape_all_jobs
from utils.logger import logger


JOB_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60
JOB_REFRESH_LOCK_KEY = "jobs:daily-refresh-lock"


def _format_job(job) -> dict:
    try:
        tags = json.loads(job.tags) if job.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = [job.tags] if job.tags else []
    job_type = getattr(job.type, "value", job.type)
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "company": job.company,
        "companyCanonical": job.companyCanonical,
        "companyType": job.companyType,
        "isProductBased": job.isProductBased,
        "isFresher": job.isFresher,
        "companyLogo": job.companyLogo,
        "type": str(job_type),
        "experience": job.experience,
        "experienceMin": job.experienceMin,
        "experienceMax": job.experienceMax,
        "salary": job.salary,
        "tags": tags,
        "applicationUrl": job.applicationUrl,
        "isRemote": job.isRemote,
        "eligibilityScope": job.eligibilityScope,
        "postedAt": job.postedAt.isoformat() if job.postedAt else None,
        "source": job.source,
        "locations": [relation.location.locationName for relation in (job.locations or [])],
    }


async def fetch_jobs(
    page: int = 1,
    type: str = "",
    keyword: str = "",
    source: str = "",
    company: str = "",
    company_type: str = "",
    remote: bool | None = None,
    page_size: int = 20,
) -> dict:
    records = await get_jobs(
        page=page,
        type=type,
        keyword=keyword,
        source=source,
        company=company,
        company_type=company_type,
        remote=remote,
        page_size=page_size,
    )
    has_more = len(records) > page_size
    formatted = [_format_job(job) for job in records[:page_size]]
    return {
        "page": page,
        "pageSize": page_size,
        "count": len(formatted),
        "hasMore": has_more,
        "jobs": formatted,
    }


async def run_job_scrape() -> dict:
    """Run one isolated refresh, guarded across multiple app workers by Redis."""

    lock = None
    acquired = True
    try:
        if redisConnection.client:
            lock = redisConnection.client.lock(
                JOB_REFRESH_LOCK_KEY,
                timeout=60 * 60,
                blocking_timeout=0,
            )
            acquired = bool(lock.acquire(blocking=False))
        if not acquired:
            logger.info("Job refresh skipped because another worker owns the lock")
            return {"status": "skipped", "reason": "already_running"}

        logger.info("Job refresh started")
        jobs = await scrape_all_jobs()
        if not jobs:
            logger.warning("Job refresh returned no accepted jobs; preserving existing records")
            return {"status": "completed", "fetched": 0, "saved": 0, "deactivated": 0}
        saved = await save_jobs(jobs)
        deactivated = await deactivate_stale_jobs()
        summary = {
            "status": "completed",
            "fetched": len(jobs),
            "saved": saved,
            "deactivated": deactivated,
        }
        logger.info(f"Job refresh complete: {summary}")
        return summary
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.error(f"Job refresh failed: {error}")
        return {"status": "failed", "error": str(error)}
    finally:
        if lock is not None and acquired:
            try:
                lock.release()
            except Exception:
                pass


async def refresh_jobs_periodically(
    interval_seconds: int = JOB_REFRESH_INTERVAL_SECONDS,
) -> None:
    """Refresh once on startup and then every 24 hours."""

    while True:
        await run_job_scrape()
        await asyncio.sleep(interval_seconds)
