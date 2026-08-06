from datetime import datetime, timedelta

from config.connection import prismaConnection
from utils.logger import database_logger


async def _upsert_location(name: str) -> str:
    record = await prismaConnection.prisma.joblocation.upsert(
        where={"locationName": name},
        data={"create": {"locationName": name}, "update": {}},
    )
    return record.id


async def save_jobs(jobs: list[dict]) -> int:
    """Upsert normalized jobs without mutating caller-owned records."""

    saved = 0
    now = datetime.utcnow()
    for incoming in jobs:
        job = dict(incoming)
        locations = list(dict.fromkeys(job.pop("locations", []) or ["India"]))
        try:
            existing = await prismaConnection.prisma.job.find_first(
                where={
                    "OR": [
                        {"canonicalKey": job["canonicalKey"]},
                        {
                            "externalId": job["externalId"],
                            "source": job["source"],
                        },
                    ]
                }
            )
            data = {
                **job,
                "lastSeenAt": now,
                "isActive": True,
            }
            if existing:
                record = await prismaConnection.prisma.job.update(
                    where={"id": existing.id}, data=data
                )
            else:
                record = await prismaConnection.prisma.job.create(data=data)

            for location in locations:
                normalized_location = str(location).strip()
                if not normalized_location:
                    continue
                location_id = await _upsert_location(normalized_location)
                await prismaConnection.prisma.jobonlocation.upsert(
                    where={
                        "jobId_locationId": {
                            "jobId": record.id,
                            "locationId": location_id,
                        }
                    },
                    data={
                        "create": {
                            "jobId": record.id,
                            "locationId": location_id,
                        },
                        "update": {},
                    },
                )
            saved += 1
        except Exception as error:
            database_logger.error(
                f"Failed to save job {job.get('externalId')} ({job.get('source')}): {error}"
            )
    return saved


async def deactivate_stale_jobs(max_age_days: int = 45) -> int:
    """Hide jobs not observed recently; records remain available for audit."""

    result = await prismaConnection.prisma.job.update_many(
        where={
            "isActive": True,
            "lastSeenAt": {"lt": datetime.utcnow() - timedelta(days=max_age_days)},
        },
        data={"isActive": False},
    )
    return result


async def get_jobs(
    page: int = 1,
    type: str = "",
    keyword: str = "",
    source: str = "",
    company: str = "",
    company_type: str = "",
    remote: bool | None = None,
    page_size: int = 20,
) -> list:
    skip = (page - 1) * page_size
    where: dict = {"isActive": True, "isFresher": True}

    if type:
        where["type"] = type.upper()
    if source:
        where["source"] = {"contains": source.casefold(), "mode": "insensitive"}
    if company:
        where["companyCanonical"] = {"contains": company, "mode": "insensitive"}
    if company_type:
        where["companyType"] = company_type.upper()
    if remote is not None:
        where["isRemote"] = remote
    if keyword:
        where["OR"] = [
            {"title": {"contains": keyword, "mode": "insensitive"}},
            {"company": {"contains": keyword, "mode": "insensitive"}},
            {"companyCanonical": {"contains": keyword, "mode": "insensitive"}},
            {"tags": {"contains": keyword, "mode": "insensitive"}},
        ]

    return await prismaConnection.prisma.job.find_many(
        where=where,  # type: ignore
        skip=skip,
        take=page_size + 1,
        order=[{"postedAt": "desc"}, {"firstSeenAt": "desc"}],
        include={"locations": {"include": {"location": True}}},
    )
