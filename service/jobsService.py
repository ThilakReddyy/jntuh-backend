import json

from database.jobOperations import get_jobs, save_jobs
from scrapers.jobScraper import scrape_all_jobs
from utils.logger import logger


def _format_job(job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "companyLogo": job.companyLogo,
        "type": job.type,
        "salary": job.salary,
        "tags": json.loads(job.tags) if job.tags else [],
        "applicationUrl": job.applicationUrl,
        "isRemote": job.isRemote,
        "postedAt": job.postedAt.strftime("%Y-%m-%d") if job.postedAt else None,
        "source": job.source,
        "locations": [jol.location.locationName for jol in (job.locations or [])],
    }


async def fetch_jobs(page: int, type: str, keyword: str, source: str) -> dict:
    jobs = await get_jobs(page=page, type=type, keyword=keyword, source=source)
    formatted = [_format_job(j) for j in jobs]
    return {
        "page": page,
        "count": len(formatted),
        "hasMore": len(formatted) == 20,
        "jobs": formatted,
    }


async def run_job_scrape():
    try:
        logger.info("Job scrape started")
        jobs = await scrape_all_jobs()
        count = await save_jobs(jobs)
        logger.info(f"Job scrape complete: {count}/{len(jobs)} saved/updated")
    except Exception as e:
        logger.error(f"Job scrape failed: {e}")
