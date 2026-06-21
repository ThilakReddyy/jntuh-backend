from config.connection import prismaConnection
from utils.logger import database_logger


async def _upsert_location(name: str) -> str:
    record = await prismaConnection.prisma.joblocation.upsert(
        where={"locationName": name},
        data={"create": {"locationName": name}, "update": {}},
    )
    return record.id


async def save_jobs(jobs: list[dict]) -> int:
    saved = 0
    for job in jobs:
        try:
            if not job.get("externalId"):
                continue
            location = job.pop("location", "Remote")

            record = await prismaConnection.prisma.job.upsert(
                where={"externalId_source": {"externalId": job["externalId"], "source": job["source"]}},
                data={
                    "create": {**job},
                    "update": {
                        "title": job["title"],
                        "salary": job.get("salary"),
                        "tags": job.get("tags"),
                        "applicationUrl": job.get("applicationUrl"),
                    },
                },
            )

            loc_id = await _upsert_location(location)
            await prismaConnection.prisma.jobonlocation.upsert(
                where={"jobId_locationId": {"jobId": record.id, "locationId": loc_id}},
                data={"create": {"jobId": record.id, "locationId": loc_id}, "update": {}},
            )
            saved += 1
        except Exception as e:
            database_logger.error(f"Failed to save job {job.get('externalId')} ({job.get('source')}): {e}")
    return saved


async def get_jobs(
    page: int = 1,
    type: str = "",
    keyword: str = "",
    source: str = "",
    page_size: int = 20,
) -> list:
    skip = (page - 1) * page_size
    where: dict = {"isRemote": True}

    if type:
        where["type"] = type.upper()
    if source:
        where["source"] = source.lower()
    if keyword:
        where["OR"] = [
            {"title": {"contains": keyword, "mode": "insensitive"}},
            {"company": {"contains": keyword, "mode": "insensitive"}},
            {"tags": {"contains": keyword, "mode": "insensitive"}},
        ]

    return await prismaConnection.prisma.job.find_many(
        where=where,  # type: ignore
        skip=skip,
        take=page_size,
        order={"postedAt": "desc"},
        include={"locations": {"include": {"location": True}}},
    )
