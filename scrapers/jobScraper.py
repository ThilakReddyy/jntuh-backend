"""Retrieve India-eligible engineering internships and fresher jobs.

Official career/ATS feeds are preferred.  Remote job boards are supplemental
and pass through the same strict engineering, early-career and India filters.
One failed provider never fails the complete refresh.
"""

import asyncio
import hashlib
import html
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup

from scrapers.jobCompanies import PRODUCT, classify_company
from utils.logger import logger


REMOTEOK_URL = "https://remoteok.com/api"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://arbeitnow.com/api/job-board-api"
AMAZON_URL = "https://www.amazon.jobs/en/search.json"
GOOGLE_URL = "https://www.google.com/about/careers/applications/jobs/results/"
AICTE_URL = "https://internship.aicte-india.org/internships.php?future=intern"
INFOSYS_URL = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs"
TCS_SEARCH_URL = "https://ibegin.tcsapps.com/candidate/api/v1/jobs/searchJ"
DELOITTE_SEARCH_URL = "https://southasiacareers.deloitte.com/search/"
TECH_MAHINDRA_URL = "https://careers.techmahindra.com/"
REMOTIVE_CATEGORIES = ("software-dev", "engineering", "data", "devops-sysadmin")

_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_USER_AGENT = "JNTUHConnectJobs/2.0 (+https://jntuhconnect.dhethi.com)"
_INDIA_TERMS = (
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "chennai",
    "mumbai", "gurugram", "gurgaon", "noida", "delhi", "ncr", "kolkata",
    "ahmedabad", "kochi", "cochin", "coimbatore", "jaipur", "chandigarh",
    "trivandrum", "thiruvananthapuram", "indore", "bhubaneswar", "india remote",
)
_GLOBAL_REMOTE_TERMS = ("worldwide", "anywhere", "global", "asia", "apac")
_EXCLUDED_REMOTE_REGIONS = ("us only", "usa only", "canada only", "uk only", "europe only", "emea only", "latam only")
_ENGINEERING_RE = re.compile(
    r"\b(?:software|developer|development|engineer(?:ing)?|sde|programmer|frontend|"
    r"front[ -]?end|backend|back[ -]?end|full[ -]?stack|mobile|android|ios|data|"
    r"machine learning|ml|artificial intelligence|ai|cloud|devops|platform|sre|"
    r"site reliability|security|cybersecurity|qa|quality assurance|sdet|test automation|"
    r"embedded|firmware|hardware|vlsi|electrical|electronics|mechanical|civil|chemical|"
    r"manufacturing|industrial|robotics|product engineer|systems? analyst|applied scientist|"
    r"research scientist|student researcher|technical intern|technology intern)\b",
    re.IGNORECASE,
)
_NON_ENGINEERING_RE = re.compile(
    r"\b(?:sales|recruiter|human resources|hr|accountant|accounting|finance|legal|"
    r"marketing|content writer|customer support|business development|talent development|"
    r"learning and development|learning & development)\b",
    re.IGNORECASE,
)
_EARLY_RE = re.compile(
    r"\b(?:intern(?:ship)?|graduate|new grad|university|campus|fresher|trainee|"
    r"apprentice|co[ -]?op|student researcher|entry[ -]?level|junior|jr\.?|associate engineer|engineer i|sde i|"
    r"software engineer 1|software engineer i)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(
    r"(?<![a-z0-9])(?:senior|sr\.?|staff|principal|lead|architect|manager|director|head|vp|"
    r"vice president)(?![a-z0-9])",
    re.IGNORECASE,
)
_AICTE_LOW_QUALITY_RE = re.compile(
    r"\b(?:course|training program|certification|enroll|admission|campus ambassador|"
    r"marketing|sales|telecall|business development|human resources|hr intern|"
    r"content writ|social media)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AtsBoard:
    company: str
    provider: str
    key: str
    base_url: str | None = None


# Only verified public boards belong in the default list. More boards can be
# supplied without a deploy through JOB_ATS_BOARDS_JSON.
DEFAULT_ATS_BOARDS = (
    AtsBoard("Razorpay", "greenhouse", "razorpaysoftwareprivatelimited"),
    AtsBoard("InMobi", "greenhouse", "inmobi"),
    AtsBoard("Postman", "greenhouse", "postman"),
    AtsBoard("PhonePe", "greenhouse", "phonepe"),
    AtsBoard("Stripe", "greenhouse", "stripe"),
    AtsBoard("Coinbase", "greenhouse", "coinbase"),
    AtsBoard("Datadog", "greenhouse", "datadog"),
    AtsBoard("Twilio", "greenhouse", "twilio"),
    AtsBoard("Meesho", "lever", "meesho"),
    AtsBoard("CRED", "lever", "cred"),
    AtsBoard("Paytm", "lever", "paytm"),
    AtsBoard("Freshworks", "lever", "freshworks"),
    # India-heavy employer boards with currently verified public postings.
    AtsBoard("Nirmata", "greenhouse", "nirmata"),
    AtsBoard("CloudSEK", "greenhouse", "cloudsek"),
    AtsBoard("Karya", "greenhouse", "karya"),
    AtsBoard("Groww", "greenhouse", "groww"),
    AtsBoard("Glance", "greenhouse", "glance"),
    AtsBoard("Stable Money", "lever", "stable-money1"),
    AtsBoard("Brainwonders", "smartrecruiters", "Brainwonders"),
    AtsBoard("Wabtec", "smartrecruiters", "Wabtec"),
    AtsBoard("Bosch", "smartrecruiters", "BoschGroup"),
    AtsBoard("Ramboll", "smartrecruiters", "Ramboll3"),
    AtsBoard("ServiceNow", "smartrecruiters", "ServiceNow"),
    AtsBoard("Renesas Electronics", "smartrecruiters", "RenesasElectronics"),
    AtsBoard("Continental", "smartrecruiters", "Continental"),
    AtsBoard("AECOM", "smartrecruiters", "AECOM2"),
    AtsBoard("Turner & Townsend", "smartrecruiters", "TurnerTownsend"),
    AtsBoard("Experian", "smartrecruiters", "Experian"),
    AtsBoard("Nagarro", "smartrecruiters", "Nagarro1"),
    AtsBoard("Sutherland", "smartrecruiters", "Sutherland"),
)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            timestamp = value / 1000 if value > 100_000_000_000 else value
            return datetime.utcfromtimestamp(timestamp)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _plain_text(value: Any, limit: int = 30000) -> str:
    if not value:
        return ""
    text = BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def _map_type(value: str) -> str:
    lowered = value.casefold()
    if any(term in lowered for term in ("intern", "apprentice", "trainee", "co-op", "coop")):
        return "INTERN"
    if "part" in lowered:
        return "PART_TIME"
    return "FULL_TIME"


def _experience_range(text: str) -> tuple[int | None, int | None]:
    normalized = text.casefold().replace("–", "-").replace("—", "-")
    ranged = re.search(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years?|yrs?)\b", normalized)
    if ranged:
        return int(ranged.group(1)), int(ranged.group(2))
    minimum = re.search(r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b", normalized)
    if minimum:
        return int(minimum.group(1)), None
    exact = re.search(r"\b(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", normalized)
    if exact:
        value = int(exact.group(1))
        return value, value
    return None, None


def _eligibility(location: str, remote: bool) -> str | None:
    lowered = location.casefold()
    if any(term in lowered for term in _INDIA_TERMS) or re.match(r"^in\s*,", lowered):
        return "INDIA_REMOTE" if remote else "INDIA_ONSITE"
    if remote and not any(term in lowered for term in _EXCLUDED_REMOTE_REGIONS):
        if any(term in lowered for term in _GLOBAL_REMOTE_TERMS):
            return "GLOBAL_REMOTE"
    return None


def _canonical_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value.strip())
        query = urlencode(
            sorted(
                (key, query_value)
                for key, query_value in parse_qsl(parsed.query, keep_blank_values=False)
                if not key.casefold().startswith("utm_")
                and key.casefold() not in {"ref", "referrer", "source", "gh_src"}
            )
        )
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/"),
                query,
                "",
            )
        )
    except ValueError:
        return value.strip()


def normalize_job(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize and filter one provider record into the database shape."""

    title = _plain_text(raw.get("title"), 500)
    company = _plain_text(raw.get("company"), 300)
    description = _plain_text(raw.get("description"))
    locations = raw.get("locations") or [raw.get("location") or ""]
    locations = [
        _plain_text(location, 300).lstrip("; ")
        for location in locations
        if location
    ]
    location_text = ", ".join(locations)
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [tags]
    structured_area = " ".join(str(tag) for tag in tags if tag)
    explicit_early_title = bool(_EARLY_RE.search(title))
    if not title or not company or not raw.get("externalId"):
        return None
    if not _ENGINEERING_RE.search(title) and not (
        explicit_early_title and _ENGINEERING_RE.search(structured_area)
    ):
        return None
    if _NON_ENGINEERING_RE.search(title) and not re.search(r"\bengineer(?:ing)?\b", title, re.I):
        return None
    if _SENIOR_RE.search(title):
        return None

    experience_text = _plain_text(raw.get("experience") or description, 10000)
    experience_min, experience_max = _experience_range(experience_text)
    is_fresher = bool(raw.get("earlyCareerHint") or explicit_early_title)
    if experience_min is not None and experience_min >= 3 and not explicit_early_title:
        return None
    if experience_max is not None and experience_max <= 2:
        is_fresher = True
    if not is_fresher:
        return None

    is_remote = bool(raw.get("isRemote"))
    scope = _eligibility(location_text, is_remote)
    if not scope:
        return None

    canonical_company, company_type = classify_company(company)
    application_url = _canonical_url(raw.get("applicationUrl"))
    canonical_material = application_url or "|".join(
        (canonical_company.casefold(), title.casefold(), location_text.casefold())
    )
    canonical_key = hashlib.sha256(canonical_material.encode("utf-8")).hexdigest()
    return {
        "externalId": str(raw["externalId"]),
        "source": str(raw.get("source") or "unknown").casefold(),
        "canonicalKey": canonical_key,
        "title": title,
        "description": description,
        "type": _map_type(f"{raw.get('type') or ''} {title}"),
        "company": company,
        "companyCanonical": canonical_company,
        "companyType": company_type,
        "isProductBased": company_type == PRODUCT,
        "isFresher": True,
        "isRemote": is_remote,
        "eligibilityScope": scope,
        "experience": raw.get("experience"),
        "experienceMin": experience_min,
        "experienceMax": experience_max,
        "companyLogo": raw.get("companyLogo"),
        "salary": raw.get("salary"),
        "tags": json.dumps([str(tag) for tag in tags[:15]]),
        "applicationUrl": application_url or None,
        "postedAt": _parse_datetime(raw.get("postedAt")),
        "locations": locations or ["India"],
    }


async def _get_json(session: aiohttp.ClientSession, url: str, **kwargs) -> Any:
    for attempt in range(3):
        try:
            async with session.get(url, timeout=_TIMEOUT, **kwargs) as response:
                if response.status == 429 or response.status >= 500:
                    if attempt == 2:
                        raise RuntimeError(f"{url} returned HTTP {response.status}")
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                    await asyncio.sleep(delay + random.random())
                    continue
                if response.status != 200:
                    raise RuntimeError(f"{url} returned HTTP {response.status}")
                if response.content_length and response.content_length > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"{url} response exceeded size limit")
                body = await response.read()
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"{url} response exceeded size limit")
                return json.loads(body)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise RuntimeError(f"{url} request failed: {error}") from error
            await asyncio.sleep((2 ** attempt) + random.random())
    return None


async def _post_json(session: aiohttp.ClientSession, url: str, **kwargs) -> Any:
    for attempt in range(3):
        try:
            async with session.post(url, timeout=_TIMEOUT, **kwargs) as response:
                if response.status == 429 or response.status >= 500:
                    if attempt == 2:
                        raise RuntimeError(f"{url} returned HTTP {response.status}")
                    await asyncio.sleep((2 ** attempt) + random.random())
                    continue
                if response.status != 200:
                    raise RuntimeError(f"{url} returned HTTP {response.status}")
                body = await response.read()
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"{url} response exceeded size limit")
                return json.loads(body)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise RuntimeError(f"{url} request failed: {error}") from error
            await asyncio.sleep((2 ** attempt) + random.random())
    return None


async def _get_html(session: aiohttp.ClientSession, url: str, **kwargs) -> str:
    for attempt in range(3):
        try:
            async with session.get(url, timeout=_TIMEOUT, **kwargs) as response:
                if response.status == 429 or response.status >= 500:
                    if attempt == 2:
                        raise RuntimeError(f"{url} returned HTTP {response.status}")
                    await asyncio.sleep((2 ** attempt) + random.random())
                    continue
                if response.status != 200:
                    raise RuntimeError(f"{url} returned HTTP {response.status}")
                body = await response.read()
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"{url} response exceeded size limit")
                return body.decode(response.charset or "utf-8", errors="replace")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            if attempt == 2:
                raise RuntimeError(f"{url} request failed: {error}") from error
            await asyncio.sleep((2 ** attempt) + random.random())
    return ""


async def _scrape_remoteok(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    data = await _get_json(session, REMOTEOK_URL)
    jobs = []
    for item in data[1:] if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        tags = item.get("tags") or []
        jobs.append({
            "externalId": item["id"], "source": "remoteok", "title": item.get("position"),
            "description": item.get("description"), "type": " ".join(map(str, tags)),
            "company": item.get("company"), "companyLogo": item.get("company_logo"),
            "isRemote": True, "tags": tags, "applicationUrl": item.get("apply_url") or item.get("url"),
            "location": item.get("location") or "Worldwide", "postedAt": item.get("epoch"),
        })
    return jobs


async def _scrape_remotive(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    jobs, seen = [], set()
    for category in REMOTIVE_CATEGORIES:
        data = await _get_json(session, REMOTIVE_URL, params={"category": category, "limit": 100})
        for item in data.get("jobs", []) if isinstance(data, dict) else []:
            external_id = str(item.get("id") or "")
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)
            jobs.append({
                "externalId": external_id, "source": "remotive", "title": item.get("title"),
                "description": item.get("description"), "type": item.get("job_type"),
                "company": item.get("company_name"), "companyLogo": item.get("company_logo"),
                "isRemote": True, "salary": item.get("salary"), "tags": item.get("tags") or [],
                "applicationUrl": item.get("url"),
                "location": item.get("candidate_required_location") or "Worldwide",
                "postedAt": item.get("publication_date"),
            })
    return jobs


async def _scrape_arbeitnow(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    data = await _get_json(session, ARBEITNOW_URL)
    jobs = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        if not item.get("slug"):
            continue
        jobs.append({
            "externalId": item["slug"], "source": "arbeitnow", "title": item.get("title"),
            "description": item.get("description"), "type": " ".join(item.get("job_types") or []),
            "company": item.get("company_name"), "isRemote": bool(item.get("remote")),
            "tags": item.get("tags") or [], "applicationUrl": item.get("url"),
            "location": item.get("location") or ("Worldwide" if item.get("remote") else ""),
            "postedAt": item.get("created_at"),
        })
    return jobs


async def _scrape_amazon(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for query in (
        "intern", "graduate engineer", "software development engineer I", "associate engineer",
        "software engineer Hyderabad", "intern Hyderabad",
    ):
        data = await _get_json(session, AMAZON_URL, params={
            "base_query": query, "country": "IND", "result_limit": 100, "offset": 0,
        })
        for item in data.get("jobs", []) if isinstance(data, dict) else []:
            external_id = str(item.get("id_icims") or item.get("id") or item.get("job_path") or "")
            if not external_id:
                continue
            location = item.get("location") or item.get("normalized_location") or "India"
            jobs[external_id] = {
                "externalId": external_id, "source": "amazon", "title": item.get("title"),
                "description": " ".join(filter(None, (
                    item.get("description"), item.get("basic_qualifications"), item.get("preferred_qualifications")
                ))),
                "company": "Amazon", "type": item.get("schedule_type") or item.get("title"),
                "isRemote": "remote" in str(location).casefold(), "location": location,
                "applicationUrl": f"https://www.amazon.jobs{item.get('job_path')}" if item.get("job_path") else None,
                "postedAt": item.get("posted_date"), "earlyCareerHint": True,
                "tags": [item.get("business_category"), item.get("job_category")],
            }
    return list(jobs.values())


async def _scrape_google(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    params = {"location": "India", "target_level": "EARLY"}
    async with session.get(GOOGLE_URL, params=params, timeout=_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"Google Careers returned HTTP {response.status}")
        body = await response.text()
    soup = BeautifulSoup(body, "html.parser")
    jobs = []
    for card in soup.select("li.lLd3Je"):
        link = card.select_one('a[href*="jobs/results/"]')
        title_node = card.select_one("h3.QJPWVe")
        if not link or not title_node:
            continue
        match = re.search(r"jobs/results/(\d+)", link.get("href", ""))
        if not match:
            continue
        locations = list(dict.fromkeys(node.get_text(" ", strip=True) for node in card.select("span.r0wTof")))
        href = link.get("href", "")
        jobs.append({
            "externalId": match.group(1), "source": "google", "title": title_node.get_text(" ", strip=True),
            "description": " ".join(node.get_text(" ", strip=True) for node in card.select("div.Xsxa1e")),
            "company": "Google", "type": title_node.get_text(" ", strip=True),
            "isRemote": any("remote" in x.casefold() for x in locations),
            "locations": locations or ["India"],
            "applicationUrl": f"https://www.google.com/about/careers/applications/{href.lstrip('./')}",
            "earlyCareerHint": True, "tags": ["Early career"],
        })
    return jobs


def _parse_infosys_jobs(data: Any) -> list[dict[str, Any]]:
    jobs = []
    for item in data if isinstance(data, list) else []:
        location = str(item.get("location") or "").strip()
        try:
            minimum = int(item.get("minExperienceLevel"))
            maximum = int(item.get("maxExperienceLevel"))
        except (TypeError, ValueError):
            continue
        if "hyderabad" not in location.casefold() or minimum > 2 or maximum > 3:
            continue
        reference = str(item.get("referenceCode") or item.get("requisitionId") or "")
        if not reference:
            continue
        description = " ".join(filter(None, (
            item.get("postingDescription"), item.get("technicalRequirement"),
            item.get("rolesResponsibilities"), item.get("preferredSkills"),
        )))
        jobs.append({
            "externalId": reference, "source": "infosys",
            "title": item.get("postingTitle"), "description": description,
            "company": item.get("company") or "Infosys", "type": item.get("roleDesignation"),
            "earlyCareerHint": True, "isRemote": False,
            "location": f"{location.title()}, India", "experience": f"{minimum}-{maximum} years",
            "applicationUrl": (
                "https://career.infosys.com/jobdesc?"
                f"jobReferenceCode={reference}&sourceId={item.get('sourceId') or 1}"
            ),
            "postedAt": item.get("createdOn"),
            "tags": [item.get("functionalArea"), item.get("unit"), item.get("educationalRequirement")],
        })
    return jobs


async def _scrape_infosys(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    data = await _get_json(
        session, INFOSYS_URL,
        params={"sourceId": "1,21", "searchText": "Hyderabad"},
        headers={
            "Origin": "https://career.infosys.com",
            "Referer": "https://career.infosys.com/",
            "User-Agent": _USER_AGENT,
        },
    )
    return _parse_infosys_jobs(data)


def _parse_tcs_jobs(items: Any) -> list[dict[str, Any]]:
    jobs = []
    for item in items if isinstance(items, list) else []:
        experience = str(item.get("experience") or "")
        minimum, maximum = _experience_range(f"{experience} years")
        external_id = str(item.get("id") or "")
        if not external_id or minimum is None or minimum > 2 or maximum is None or maximum > 4:
            continue
        jobs.append({
            "externalId": external_id, "source": "tcs", "title": item.get("jobTitle"),
            "description": " | ".join(filter(None, (
                f"Skills: {item.get('skills')}" if item.get("skills") else None,
                f"Function: {item.get('functionName')}" if item.get("functionName") else None,
                f"Apply by: {item.get('applyByDate')}" if item.get("applyByDate") else None,
            ))),
            "company": "TCS", "type": item.get("functionName") or item.get("jobTitle"),
            "earlyCareerHint": True, "isRemote": False,
            "location": f"{item.get('location') or 'Hyderabad'}, India", "experience": f"{experience} years",
            "applicationUrl": f"https://ibegin.tcsapps.com/candidate/next/en-IN/jobs/{external_id}",
            "tags": [item.get("functionName"), item.get("skills")],
        })
    unique = {}
    for job in jobs:
        key = (
            str(job.get("title") or "").casefold(),
            str(job.get("location") or "").casefold(),
            str(job.get("experience") or "").casefold(),
        )
        unique[key] = job
    return list(unique.values())


async def _scrape_tcs(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    jobs, page, total_pages = [], 1, 1
    while page <= total_pages and page <= 50:
        payload = {
            "jobTitle": None, "jobCity": "Hyderabad", "jobFunction": None,
            "jobExperience": None, "jobSkill": None, "pageNumber": str(page),
            "userText": "", "jobTitleOrder": None, "jobCityOrder": None,
            "jobFunctionOrder": None, "jobExperienceOrder": None, "applyByOrder": None,
            "regular": True, "walkin": True,
        }
        response = await _post_json(session, TCS_SEARCH_URL, json=payload)
        data = response.get("data", {}) if isinstance(response, dict) else {}
        items = data.get("jobs", [])
        jobs.extend(_parse_tcs_jobs(items))
        total = int(data.get("totalJobs") or 0)
        total_pages = max(1, (total + 9) // 10)
        if not items:
            break
        page += 1
    return list({
        (
            str(job.get("title") or "").casefold(),
            str(job.get("location") or "").casefold(),
            str(job.get("experience") or "").casefold(),
        ): job
        for job in jobs
    }.values())


def _parse_deloitte_search(body: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    results = []
    for row in soup.select("tr.data-row"):
        link = row.select_one("a.jobTitle-link")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        if not _ENGINEERING_RE.search(title) or _SENIOR_RE.search(title):
            continue
        href = urljoin(DELOITTE_SEARCH_URL, str(link.get("href") or ""))
        external_match = re.search(r"/(\d+)/?$", urlsplit(href).path)
        if not external_match:
            continue
        location_node = row.select_one("td.colLocation .jobLocation")
        date_node = row.select_one("td.colDate .jobDate")
        posted_at = None
        if date_node:
            try:
                posted_at = datetime.strptime(date_node.get_text(" ", strip=True), "%b %d, %Y")
            except ValueError:
                pass
        results.append({
            "externalId": external_match.group(1), "source": "deloitte", "title": title,
            "company": "Deloitte", "type": title, "earlyCareerHint": True,
            "isRemote": False,
            "location": (location_node.get_text(" ", strip=True) if location_node else "Hyderabad, IN"),
            "applicationUrl": href, "postedAt": posted_at,
            "tags": ["Engineering", "Analyst"],
        })
    return results


async def _scrape_deloitte(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for query in ("analyst", "associate", "intern", "graduate"):
        for startrow in (0, 25):
            body = await _get_html(session, DELOITTE_SEARCH_URL, params={
                "q": query, "locationsearch": "Hyderabad", "startrow": startrow,
            })
            page = _parse_deloitte_search(body)
            for item in page:
                summaries[item["externalId"]] = item
            if len(BeautifulSoup(body, "html.parser").select("tr.data-row")) < 25:
                break

    async def add_description(item: dict[str, Any]) -> dict[str, Any]:
        detail = BeautifulSoup(await _get_html(session, item["applicationUrl"]), "html.parser")
        container = detail.select_one(".jobdescription, .jobDescription, .job, main") or detail
        item["description"] = container.get_text(" ", strip=True)[:30000]
        return item

    results = await asyncio.gather(
        *(add_description(item) for item in summaries.values()), return_exceptions=True,
    )
    jobs = []
    for summary, result in zip(summaries.values(), results):
        if isinstance(result, BaseException):
            summary["description"] = summary["title"]
            jobs.append(summary)
        else:
            jobs.append(result)
    return jobs


def _parse_tech_mahindra_jobs(body: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    jobs = []
    for link in soup.select('#ctl00_ContentPlaceHolder1_divTechnicaljobs a[href*="JobDetails.aspx"]'):
        card = link.find_parent("div", class_="title2")
        if not card:
            continue
        title_node = card.select_one(":scope > div > div")
        details = card.select_one("p")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        detail_text = details.get_text(" ", strip=True) if details else ""
        experience_match = re.search(r"Experience:\s*([0-9]+\s*(?:-|to)\s*[0-9]+\s*Years?)", detail_text, re.I)
        location_match = re.search(r"Location:\s*(.+)$", detail_text, re.I)
        experience = experience_match.group(1) if experience_match else ""
        minimum, _ = _experience_range(experience)
        if minimum is None or minimum > 2:
            continue
        href = urljoin(TECH_MAHINDRA_URL, str(link.get("href") or ""))
        jobs.append({
            "externalId": hashlib.sha256(href.encode("utf-8")).hexdigest()[:32],
            "source": "tech-mahindra", "title": title, "description": detail_text,
            "company": "Tech Mahindra", "type": title, "earlyCareerHint": True,
            "isRemote": False,
            "location": f"{location_match.group(1).strip() if location_match else 'Hyderabad'}, India",
            "experience": experience, "applicationUrl": href, "tags": ["IT"],
        })
    return jobs


async def _scrape_tech_mahindra(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    return _parse_tech_mahindra_jobs(await _get_html(session, TECH_MAHINDRA_URL))


def _portal_date(value: str) -> datetime | None:
    for date_format in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), date_format)
        except ValueError:
            continue
    return None


async def _scrape_aicte(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """Read the official AICTE India portal without crawling detail pages.

    The index contains many incomplete promotional records, so only active,
    paid engineering cards with a named employer are admitted here. The normal
    pipeline applies its engineering/India checks again afterward.
    """

    async with session.get(AICTE_URL, timeout=_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"AICTE internship portal returned HTTP {response.status}")
        if response.content_length and response.content_length > _MAX_RESPONSE_BYTES:
            raise RuntimeError("AICTE internship portal response exceeded size limit")
        body = await response.read()
        if len(body) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("AICTE internship portal response exceeded size limit")

    soup = BeautifulSoup(body, "html.parser")
    today = datetime.utcnow().date()
    jobs = []
    for card in soup.select(".card.internship-item"):
        def card_text(selector: str) -> str:
            node = card.select_one(selector)
            return node.get_text(" ", strip=True) if node else ""

        title = card_text(".job-title")
        company = card_text(".company-name")
        location = card_text(".location span") or "India"
        stipend = card_text(".stipend span")
        apply_by = _portal_date(card_text(".apply-by span"))
        posted_at = _portal_date(card_text(".posted-on span"))
        detail_link = card.select_one('a[href*="internship-details.php"]')
        stipend_values = [int(value) for value in re.findall(r"\d+", stipend.replace(",", ""))]

        if (
            not title
            or not company
            or len(title) > 180
            or not detail_link
            or not apply_by
            or apply_by.date() < today
            or not stipend_values
            or max(stipend_values) <= 0
            or not _ENGINEERING_RE.search(title)
            or _AICTE_LOW_QUALITY_RE.search(title)
        ):
            continue

        href = str(detail_link.get("href") or "")
        job_url = urljoin(AICTE_URL, href)
        jobs.append({
            "externalId": hashlib.sha256(href.encode("utf-8")).hexdigest()[:32],
            "source": "aicte", "title": title, "company": company,
            "description": " | ".join(filter(None, (
                f"Official AICTE internship listing. Apply by {apply_by:%d %b %Y}.",
                f"Duration: {card_text('.duration span')}",
                f"Start date: {card_text('.start-date span')}",
            ))),
            "type": "internship", "earlyCareerHint": True,
            "isRemote": "virtual" in card_text(".wfh span").casefold(),
            "location": f"{location}, India", "salary": stipend,
            "applicationUrl": job_url, "postedAt": posted_at,
            "tags": ["AICTE", "Engineering Internship"],
        })
    return jobs


def _ats_boards() -> tuple[AtsBoard, ...]:
    configured = os.getenv("JOB_ATS_BOARDS_JSON")
    if not configured:
        return DEFAULT_ATS_BOARDS
    try:
        entries = json.loads(configured)
        extra = tuple(AtsBoard(**entry) for entry in entries)
        return DEFAULT_ATS_BOARDS + extra
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        logger.warning(f"Ignoring invalid JOB_ATS_BOARDS_JSON: {error}")
        return DEFAULT_ATS_BOARDS


async def _scrape_ats_board(session: aiohttp.ClientSession, board: AtsBoard) -> list[dict[str, Any]]:
    provider = board.provider.casefold()
    if provider == "greenhouse":
        data = await _get_json(session, board.base_url or f"https://boards-api.greenhouse.io/v1/boards/{board.key}/jobs", params={"content": "true"})
        return [{
            "externalId": item.get("id"), "source": f"greenhouse:{board.key}", "title": item.get("title"),
            "description": item.get("content"), "company": board.company, "type": item.get("title"),
            "isRemote": "remote" in str(item.get("location", {}).get("name", "")).casefold(),
            "location": item.get("location", {}).get("name", ""), "applicationUrl": item.get("absolute_url"),
            "postedAt": item.get("first_published"),
            "tags": [department.get("name") for department in item.get("departments", [])],
        } for item in data.get("jobs", [])]
    if provider == "lever":
        endpoint = board.base_url or f"https://api.lever.co/v0/postings/{board.key}"
        data = []
        for skip in range(0, 1000, 100):
            page = await _get_json(
                session,
                endpoint,
                params={"mode": "json", "limit": 100, "skip": skip},
            )
            if not isinstance(page, list):
                raise RuntimeError(f"Lever board {board.key} returned an invalid payload")
            data.extend(page)
            if len(page) < 100:
                break
        return [{
            "externalId": item.get("id"), "source": f"lever:{board.key}", "title": item.get("text"),
            "description": item.get("descriptionPlain") or item.get("description"), "company": board.company,
            "type": item.get("categories", {}).get("commitment", ""),
            "isRemote": (
                "remote" in str(item.get("categories", {}).get("location", "")).casefold()
                or str(item.get("workplaceType", "")).casefold() == "remote"
            ),
            "locations": item.get("categories", {}).get("allLocations") or [item.get("categories", {}).get("location", "")],
            "applicationUrl": item.get("applyUrl") or item.get("hostedUrl"),
            "postedAt": item.get("createdAt"), "tags": [item.get("categories", {}).get("team", "")],
        } for item in data if isinstance(item, dict)]
    if provider == "ashby":
        data = await _get_json(session, board.base_url or f"https://api.ashbyhq.com/posting-api/job-board/{board.key}", params={"includeCompensation": "true"})
        return [{
            "externalId": item.get("jobUrl") or item.get("applyUrl"), "source": f"ashby:{board.key}",
            "title": item.get("title"), "description": item.get("descriptionPlain") or item.get("descriptionHtml"),
            "company": board.company, "type": item.get("employmentType", ""),
            "isRemote": bool(item.get("isRemote")), "location": item.get("location", ""),
            "locations": [item.get("location", "")] + [x.get("location", "") for x in item.get("secondaryLocations", [])],
            "applicationUrl": item.get("applyUrl") or item.get("jobUrl"), "postedAt": item.get("publishedAt"),
            "salary": (item.get("compensation") or {}).get("scrapeableCompensationSalarySummary"),
            "tags": [item.get("department", ""), item.get("team", "")],
        } for item in data.get("jobs", [])]
    if provider == "smartrecruiters":
        endpoint = board.base_url or f"https://api.smartrecruiters.com/v1/companies/{board.key}/postings"
        summaries = []
        for offset in range(0, 1000, 100):
            page = await _get_json(session, endpoint, params={
                "limit": 100, "offset": offset, "country": "in",
            })
            content = page.get("content", []) if isinstance(page, dict) else []
            summaries.extend(content)
            if offset + len(content) >= int(page.get("totalFound", len(summaries))):
                break

        cutoff = datetime.utcnow() - timedelta(days=180)
        candidates = []
        for item in summaries:
            title = str(item.get("name") or "")
            employment = item.get("typeOfEmployment") or {}
            experience = item.get("experienceLevel") or {}
            released_at = _parse_datetime(item.get("releasedDate"))
            structured_early = (
                str(employment.get("id") or "").casefold() == "intern"
                or str(experience.get("id") or "").casefold() == "entry_level"
                or bool(_EARLY_RE.search(title))
            )
            if (
                item.get("id")
                and _ENGINEERING_RE.search(title)
                and structured_early
                and not _SENIOR_RE.search(title)
                and (released_at is None or released_at >= cutoff)
            ):
                candidates.append(item)

        async def fetch_detail(item: dict[str, Any]) -> dict[str, Any]:
            detail = await _get_json(session, f"{endpoint}/{item['id']}")
            return detail if isinstance(detail, dict) else item

        details = await asyncio.gather(*(fetch_detail(item) for item in candidates))
        jobs = []
        for summary, detail in zip(candidates, details):
            sections = ((detail.get("jobAd") or {}).get("sections") or {})
            description = " ".join(
                str((sections.get(section) or {}).get("text") or "")
                for section in (
                    "companyDescription", "jobDescription", "qualifications", "additionalInformation"
                )
            )
            location = detail.get("location") or summary.get("location") or {}
            employment = detail.get("typeOfEmployment") or summary.get("typeOfEmployment") or {}
            experience = detail.get("experienceLevel") or summary.get("experienceLevel") or {}
            function = detail.get("function") or summary.get("function") or {}
            department = detail.get("department") or summary.get("department") or {}
            jobs.append({
                "externalId": detail.get("id") or summary.get("id"),
                "source": f"smartrecruiters:{board.key}",
                "title": detail.get("name") or summary.get("name"),
                "description": description,
                "company": (detail.get("company") or summary.get("company") or {}).get("name") or board.company,
                "type": employment.get("label") or employment.get("id") or "",
                "earlyCareerHint": True,
                "isRemote": bool(location.get("remote")),
                "location": location.get("fullLocation") or ", ".join(filter(None, (
                    location.get("city"), location.get("region"), "India"
                ))),
                "applicationUrl": detail.get("applyUrl") or detail.get("postingUrl"),
                "postedAt": detail.get("releasedDate") or summary.get("releasedDate"),
                "tags": [
                    function.get("label", ""), department.get("label", ""),
                    experience.get("label", ""), employment.get("label", ""),
                ],
            })
        return jobs
    raise RuntimeError(f"Unsupported ATS provider: {board.provider}")


async def scrape_all_jobs() -> list[dict[str, Any]]:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json,text/html;q=0.9"}
    connector = aiohttp.TCPConnector(limit=12, limit_per_host=3)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        sources = [
            ("amazon", _scrape_amazon(session)),
            ("google", _scrape_google(session)),
            ("infosys", _scrape_infosys(session)),
            ("tcs", _scrape_tcs(session)),
            ("deloitte", _scrape_deloitte(session)),
            ("tech-mahindra", _scrape_tech_mahindra(session)),
            ("remoteok", _scrape_remoteok(session)),
            ("remotive", _scrape_remotive(session)),
            ("arbeitnow", _scrape_arbeitnow(session)),
            ("aicte", _scrape_aicte(session)),
            *((f"{board.provider}:{board.key}", _scrape_ats_board(session, board)) for board in _ats_boards()),
        ]
        results = await asyncio.gather(*(source[1] for source in sources), return_exceptions=True)

    accepted: dict[str, dict[str, Any]] = {}
    for (source_name, _), result in zip(sources, results):
        if isinstance(result, BaseException):
            logger.warning(f"Job source {source_name} failed: {result}")
            continue
        source_accepted = 0
        for raw_job in result:
            normalized = normalize_job(raw_job)
            if normalized and normalized["canonicalKey"] not in accepted:
                accepted[normalized["canonicalKey"]] = normalized
                source_accepted += 1
        logger.info(f"Job source {source_name}: {len(result)} fetched, {source_accepted} accepted")

    logger.info(f"Job refresh accepted {len(accepted)} unique India early-career engineering jobs")
    return list(accepted.values())
