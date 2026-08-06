from scrapers.jobCompanies import PRODUCT, SERVICE, classify_company
from scrapers.jobScraper import (
    _parse_deloitte_search,
    _parse_infosys_jobs,
    _parse_tcs_jobs,
    _parse_tech_mahindra_jobs,
    normalize_job,
)


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
    assert normalize_job(_job(title="Engineering_Senior Consultant_Hyderabad")) is None
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
    assert classify_company("Experian India") == ("Experian", PRODUCT)
    assert classify_company("Sutherland Global Services") == ("Sutherland", SERVICE)


def test_infosys_parser_keeps_only_hyderabad_roles_with_entry_level_minimum():
    jobs = _parse_infosys_jobs([
        {
            "postingTitle": "Python Developer", "company": "Infosys Limited",
            "location": "HYDERABAD", "minExperienceLevel": 2, "maxExperienceLevel": 3,
            "referenceCode": "INFSYS-EXTERNAL-1", "sourceId": 1,
            "postingDescription": "Build software", "functionalArea": "Engineering Services",
        },
        {
            "postingTitle": "Cloud Engineer", "company": "Infosys Limited",
            "location": "PUNE", "minExperienceLevel": 1, "maxExperienceLevel": 2,
            "referenceCode": "INFSYS-EXTERNAL-2",
        },
        {
            "postingTitle": "Java Developer", "company": "Infosys Limited",
            "location": "HYDERABAD", "minExperienceLevel": 4, "maxExperienceLevel": 7,
            "referenceCode": "INFSYS-EXTERNAL-3",
        },
    ])

    assert [job["externalId"] for job in jobs] == ["INFSYS-EXTERNAL-1"]
    assert jobs[0]["experience"] == "2-3 years"


def test_tcs_parser_rejects_experienced_roles_and_preserves_official_range():
    jobs = _parse_tcs_jobs([
        {"id": "1J", "jobTitle": "Software Engineer", "location": "Hyderabad", "experience": "1-3"},
        {"id": "2J", "jobTitle": "Cloud Engineer", "location": "Hyderabad", "experience": "5-8"},
    ])

    assert len(jobs) == 1
    assert jobs[0]["externalId"] == "1J"
    assert jobs[0]["experience"] == "1-3 years"


def test_deloitte_search_parser_reads_engineering_analyst_row():
    body = """
    <table><tr class="data-row">
      <td class="colTitle"><a class="jobTitle-link" href="/job/hyd-ai/12345/">Analyst | Generative AI | Engineering</a></td>
      <td class="colLocation"><span class="jobLocation">Hyderabad, IN</span></td>
      <td class="colDate"><span class="jobDate">Aug 05, 2026</span></td>
    </tr></table>
    """

    jobs = _parse_deloitte_search(body)

    assert len(jobs) == 1
    assert jobs[0]["externalId"] == "12345"
    assert jobs[0]["location"] == "Hyderabad, IN"


def test_tech_mahindra_parser_keeps_only_early_career_cards():
    body = """
    <div id="ctl00_ContentPlaceHolder1_divTechnicaljobs">
      <div class="title2"><div><span>IT</span><div>Junior Software Engineer</div>
      <p><b>Skills:</b> Python<br><b>Experience:</b> 0 - 2 Years<br><b>Location:</b> HYDERABAD</p>
      <a href="JobDetails.aspx?JobCode=early">Apply</a></div></div>
      <div class="title2"><div><span>IT</span><div>Software Engineer</div>
      <p><b>Skills:</b> Java<br><b>Experience:</b> 5 - 8 Years<br><b>Location:</b> HYDERABAD</p>
      <a href="JobDetails.aspx?JobCode=senior">Apply</a></div></div>
    </div>
    """

    jobs = _parse_tech_mahindra_jobs(body)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Junior Software Engineer"
