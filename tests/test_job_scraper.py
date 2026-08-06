from scrapers.jobCompanies import PRODUCT, SERVICE, classify_company
from scrapers.jobScraper import normalize_job


def _job(**overrides):
    job = {
        "externalId": "job-1",
        "source": "test",
        "title": "Software Engineering Intern",
        "description": "Build production software with our engineering team.",
        "company": "Facebook India",
        "type": "internship",
        "isRemote": False,
        "location": "Hyderabad, India",
        "applicationUrl": "https://careers.example/jobs/1?utm_source=test",
    }
    job.update(overrides)
    return job


def test_normalize_job_accepts_india_engineering_intern_and_marks_product_company():
    result = normalize_job(_job())

    assert result is not None
    assert result["type"] == "INTERN"
    assert result["companyCanonical"] == "Meta"
    assert result["companyType"] == "PRODUCT"
    assert result["isProductBased"] is True
    assert result["eligibilityScope"] == "INDIA_ONSITE"
    assert result["applicationUrl"] == "https://careers.example/jobs/1"


def test_normalize_job_preserves_greenhouse_job_id_but_removes_tracking_query():
    result = normalize_job(
        _job(
            applicationUrl=(
                "https://company.example/careers/search?gh_jid=12345"
                "&gh_src=campus&utm_source=newsletter"
            )
        )
    )

    assert result is not None
    assert result["applicationUrl"] == (
        "https://company.example/careers/search?gh_jid=12345"
    )


def test_normalize_job_rejects_senior_and_non_engineering_roles():
    assert normalize_job(_job(title="Senior Software Engineer")) is None
    assert normalize_job(_job(title="Marketing Intern")) is None


def test_normalize_job_accepts_global_remote_early_career_role():
    result = normalize_job(
        _job(
            title="Junior Backend Developer",
            company="Example Co",
            isRemote=True,
            location="Remote - Worldwide",
        )
    )

    assert result is not None
    assert result["eligibilityScope"] == "GLOBAL_REMOTE"


def test_normalize_job_rejects_remote_role_restricted_outside_india():
    assert normalize_job(
        _job(isRemote=True, location="Remote - US only")
    ) is None


def test_generic_intern_title_uses_structured_engineering_team_and_maps_trainee():
    result = normalize_job(
        _job(
            title="Intern Trainee",
            type="trainee",
            tags=["Core Engineering"],
            location="IN, TS, Hyderabad",
            description="Work with the platform team. One section mentions 5+ years elsewhere.",
        )
    )

    assert result is not None
    assert result["type"] == "INTERN"
    assert result["eligibilityScope"] == "INDIA_ONSITE"


def test_structured_intern_type_accepts_engineering_title_without_intern_in_title():
    result = normalize_job(
        _job(
            title="AI Engineer",
            type="Intern",
            earlyCareerHint=True,
            company="Brainwonders",
            location="Mumbai, MH, India",
        )
    )

    assert result is not None
    assert result["type"] == "INTERN"
    assert result["companyType"] == "SERVICE"


def test_explicit_company_aliases_classify_product_and_service_companies():
    assert classify_company("Amazon Web Services India") == ("Amazon", PRODUCT)
    assert classify_company("Tata Consultancy Services Limited") == ("TCS", SERVICE)
