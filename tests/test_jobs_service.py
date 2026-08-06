import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from service import jobsService


def _record(tags='["python", "backend"]'):
    location = SimpleNamespace(location=SimpleNamespace(locationName="Hyderabad, India"))
    return SimpleNamespace(
        id="job-1",
        title="Software Engineer I",
        description="Build APIs",
        company="Amazon",
        companyCanonical="Amazon",
        companyType="PRODUCT",
        isProductBased=True,
        isFresher=True,
        companyLogo=None,
        type="FULL_TIME",
        experience="0-2 years",
        experienceMin=0,
        experienceMax=2,
        salary=None,
        tags=tags,
        applicationUrl="https://example.test/apply",
        isRemote=False,
        eligibilityScope="INDIA_ONSITE",
        postedAt=datetime(2026, 8, 1, 12, 0),
        source="amazon",
        locations=[location],
    )


def test_fetch_jobs_uses_lookahead_for_accurate_has_more(monkeypatch):
    records = [_record() for _ in range(3)]
    get_jobs = AsyncMock(return_value=records)
    monkeypatch.setattr(jobsService, "get_jobs", get_jobs)

    result = asyncio.run(jobsService.fetch_jobs(page=1, page_size=2))

    assert result["count"] == 2
    assert result["hasMore"] is True
    assert len(result["jobs"]) == 2
    get_jobs.assert_awaited_once()


def test_format_job_tolerates_legacy_malformed_tags():
    result = jobsService._format_job(_record(tags="python"))

    assert result["tags"] == ["python"]
    assert result["isProductBased"] is True
    assert result["locations"] == ["Hyderabad, India"]


def test_run_job_scrape_preserves_records_when_every_source_is_empty(monkeypatch):
    monkeypatch.setattr(jobsService.redisConnection, "client", None)
    monkeypatch.setattr(jobsService, "scrape_all_jobs", AsyncMock(return_value=[]))
    save_jobs = AsyncMock()
    deactivate = AsyncMock()
    monkeypatch.setattr(jobsService, "save_jobs", save_jobs)
    monkeypatch.setattr(jobsService, "deactivate_stale_jobs", deactivate)

    result = asyncio.run(jobsService.run_job_scrape())

    assert result == {"status": "completed", "fetched": 0, "saved": 0, "deactivated": 0}
    save_jobs.assert_not_awaited()
    deactivate.assert_not_awaited()

