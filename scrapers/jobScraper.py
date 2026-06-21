import asyncio
import json
import aiohttp
from datetime import datetime

from utils.logger import logger

REMOTEOK_URL = "https://remoteok.com/api"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://arbeitnow.com/api/job-board-api"

REMOTIVE_CATEGORIES = ["software-dev", "engineering", "data", "devops-sysadmin"]
_TIMEOUT = aiohttp.ClientTimeout(total=20)


def _map_type(raw: str) -> str:
    raw = raw.lower()
    if "intern" in raw:
        return "INTERN"
    if "part" in raw:
        return "PART_TIME"
    return "FULL_TIME"


async def _scrape_remoteok(session: aiohttp.ClientSession) -> list[dict]:
    jobs = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JNTUHResultsBot/1.0)"}
        async with session.get(REMOTEOK_URL, headers=headers, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning(f"RemoteOK returned {resp.status}")
                return []
            data = await resp.json(content_type=None)
            for item in data[1:]:  # index 0 is a legal notice object
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                tags = item.get("tags") or []
                s_min, s_max = item.get("salary_min"), item.get("salary_max")
                salary = None
                if s_min and s_max:
                    salary = f"${int(s_min):,} – ${int(s_max):,}/yr"
                elif s_min:
                    salary = f"From ${int(s_min):,}/yr"

                jobs.append(
                    {
                        "externalId": str(item["id"]),
                        "source": "remoteok",
                        "title": item.get("position", ""),
                        "description": item.get("description", ""),
                        "type": _map_type(" ".join(str(t) for t in tags)),
                        "company": item.get("company", ""),
                        "companyLogo": item.get("company_logo"),
                        "isRemote": True,
                        "salary": salary,
                        "tags": json.dumps(tags[:10]),
                        "applicationUrl": item.get("apply_url") or item.get("url"),
                        "location": item.get("location") or "Remote",
                        "postedAt": datetime.utcfromtimestamp(item["epoch"])
                        if item.get("epoch")
                        else None,
                    }
                )
    except Exception as e:
        logger.error(f"RemoteOK scrape error: {e}")
    logger.info(f"RemoteOK: {len(jobs)} jobs fetched")
    return jobs


async def _scrape_remotive(session: aiohttp.ClientSession) -> list[dict]:
    jobs = []
    seen: set[str] = set()
    try:
        for category in REMOTIVE_CATEGORIES:
            url = f"{REMOTIVE_URL}?category={category}&limit=100"
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                for item in data.get("jobs", []):
                    ext_id = str(item.get("id", ""))
                    if not ext_id or ext_id in seen:
                        continue
                    seen.add(ext_id)

                    tags = item.get("tags") or []
                    pub_date = None
                    raw_date = item.get("publication_date")
                    if raw_date:
                        try:
                            pub_date = datetime.fromisoformat(
                                raw_date.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            pass

                    jobs.append(
                        {
                            "externalId": ext_id,
                            "source": "remotive",
                            "title": item.get("title", ""),
                            "description": item.get("description", ""),
                            "type": _map_type(item.get("job_type", "full_time")),
                            "company": item.get("company_name", ""),
                            "companyLogo": item.get("company_logo"),
                            "isRemote": True,
                            "salary": item.get("salary"),
                            "tags": json.dumps(tags[:10]),
                            "applicationUrl": item.get("url"),
                            "location": item.get("candidate_required_location")
                            or "Remote",
                            "postedAt": pub_date,
                        }
                    )
    except Exception as e:
        logger.error(f"Remotive scrape error: {e}")
    logger.info(f"Remotive: {len(jobs)} jobs fetched")
    return jobs


async def _scrape_arbeitnow(session: aiohttp.ClientSession) -> list[dict]:
    jobs = []
    try:
        async with session.get(ARBEITNOW_URL, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning(f"Arbeitnow returned {resp.status}")
                return []
            data = await resp.json()
            for item in data.get("data", []):
                if not item.get("remote", False):
                    continue
                slug = item.get("slug", "")
                if not slug:
                    continue
                tags = item.get("tags") or []
                job_types = item.get("job_types") or ["full_time"]

                posted_at = None
                if item.get("created_at"):
                    try:
                        posted_at = datetime.utcfromtimestamp(item["created_at"])
                    except Exception:
                        pass

                jobs.append(
                    {
                        "externalId": slug,
                        "source": "arbeitnow",
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "type": _map_type(job_types[0]),
                        "company": item.get("company_name", ""),
                        "companyLogo": None,
                        "isRemote": True,
                        "salary": None,
                        "tags": json.dumps(tags[:10]),
                        "applicationUrl": item.get("url"),
                        "location": "Remote",
                        "postedAt": posted_at,
                    }
                )
    except Exception as e:
        logger.error(f"Arbeitnow scrape error: {e}")
    logger.info(f"Arbeitnow: {len(jobs)} jobs fetched")
    return jobs


async def scrape_all_jobs() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            _scrape_remoteok(session),
            _scrape_remotive(session),
            _scrape_arbeitnow(session),
            return_exceptions=True,
        )

    all_jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)

    logger.info(f"Job scraper total: {len(all_jobs)} jobs across 3 sources")
    return all_jobs
