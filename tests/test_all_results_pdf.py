import asyncio
import copy
from io import BytesIO
import os
import re
from pathlib import Path
import sys

import pytest
from fastapi.responses import JSONResponse
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name, value in {
    "RABBITMQ_URL": "amqp://guest:guest@localhost/",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/jntuh",
    "QUEUE_NAME": "test", "REDIS_URL": "redis://localhost:6379/0",
    "VAPID_PUBLIC_KEY": "test", "VAPID_PRIVATE_KEY": "test",
    "TELEGRAM_TOKEN": "test", "TELEGRAM_CHAT_ID": "test",
    "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1", "S3_BUCKET_NAME": "test",
    "GRACE_MARKS_ADMIN_KEY": "test",
}.items():
    os.environ.setdefault(name, value)

from service import getAllResultPDFService  # noqa: E402
from service.all_results_pdf import generate_all_results_pdf  # noqa: E402


def subject(code, grade="A", name="Mathematics", credits=4):
    return {"subjectCode": code, "subjectName": name, "grades": grade,
            "internalMarks": 25, "externalMarks": 55, "totalMarks": 80, "credits": credits}


PAYLOAD = {
    "details": {"name": "Test Student", "rollNumber": "22XX1A0501",
                "collegeCode": "XX", "branch": "Computer Science and Engineering"},
    "results": [
        {"semester": "1-1", "exams": [
            {"examCode": "1001", "rcrv": False, "graceMarks": False,
             "subjects": [subject("FAILED101", "F", credits=0), subject("PASS102")]},
            {"examCode": "1001[RCRV]", "rcrv": True, "graceMarks": False,
             "subjects": [subject("REVALUED101", "A+")]},
            {"examCode": "1002[Grace]", "rcrv": False, "graceMarks": True,
             "subjects": [subject("GRACE101", "C")]},
        ]},
        {"semester": "1-2", "exams": [
            {"examCode": "2001", "subjects": [subject("SECOND201", "O")]},
        ]},
    ],
}


def pages(payload):
    return [page.extract_text() for page in PdfReader(BytesIO(generate_all_results_pdf(payload))).pages]


def test_every_exam_and_variant_gets_its_own_page():
    result = pages(PAYLOAD)
    assert len(result) == 4
    for page, exam_code, code in zip(result, ["1001", "1001[RCRV]", "1002[Grace]", "2001"],
                                     ["FAILED101", "REVALUED101", "GRACE101", "SECOND201"]):
        assert f"EXAM CODE: {exam_code}\n" in page
        assert code in "".join(page.split())
        assert "22XX1A0501" in page
    assert "REVALUED101" not in result[0]
    assert "FAILED101" not in result[1]
    assert "Registered Subjects: 2" in result[0]
    assert "Passed: 1" in result[0]
    assert "Recorded Credits: 4" in result[0]
    assert "SEMESTER: 1-2" in result[-1]


def test_long_exam_continues_without_losing_subjects_or_mixing_exams():
    payload = copy.deepcopy(PAYLOAD)
    payload["results"][0]["exams"][0]["subjects"] = [
        subject(f"SUB{i:03}", name="Advanced Engineering Mathematics & Computing <Theory> " * 3)
        for i in range(40)
    ]
    result = pages(payload)
    first_exam_pages = [page for page in result if "EXAM CODE: 1001\n" in page]
    assert len(first_exam_pages) > 1
    text = "\n".join(first_exam_pages)
    for i in range(40):
        assert text.count(f"SUB{i:03}") == 1
    assert "<Theory>" in text
    assert "Registered Subjects: 40" in text
    for page in first_exam_pages:
        assert "SUBJECT TITLE" in page
        assert "REVALUED101" not in page
    assert "EXAM CODE: 1001[RCRV]" in result[len(first_exam_pages)]


def test_absent_unknown_and_zero_credit_pass_are_not_miscounted():
    payload = copy.deepcopy(PAYLOAD)
    payload["results"][0]["exams"][0]["subjects"] = [
        subject("ABSENT", "Ab", credits=0), subject("UNKNOWN", "-", credits=0),
        subject("MANDATORY", "P", credits=0),
    ]
    page = pages(payload)[0]
    assert "Passed: 1" in page
    assert "Recorded Credits: 0" in page


def test_pharmacy_grade_points_use_existing_regulation_scale():
    payload = copy.deepcopy(PAYLOAD)
    payload["details"]["rollNumber"] = "23XX1R0001"
    assert re.search(r"\bA\s+9\s+4\b", pages(payload)[0])
    assert re.search(r"\bA\s+8\s+4\b", pages(PAYLOAD)[0])


@pytest.mark.parametrize("missing", [None, "", "-", 0, "0", "0.00"])
def test_exam_without_marks_omits_mark_columns_only_for_that_exam(missing):
    payload = copy.deepcopy(PAYLOAD)
    for row in payload["results"][0]["exams"][0]["subjects"]:
        for key in ("internalMarks", "externalMarks", "totalMarks"):
            row[key] = missing
    result = pages(payload)
    for heading in ("INT.", "EXT.", "TOTAL"):
        assert heading not in result[0]
        assert heading in result[1]
    assert "GRADE" in result[0]
    assert "CREDITS" in result[0]
    assert "GRADE POINTS:" not in result[0]


@pytest.mark.parametrize("key, heading", [("internalMarks", "INT."), ("externalMarks", "EXT."), ("totalMarks", "TOTAL")])
def test_mark_column_is_kept_when_any_subject_has_a_value(key, heading):
    payload = copy.deepcopy(PAYLOAD)
    rows = payload["results"][0]["exams"][0]["subjects"]
    for row in rows:
        for field in ("internalMarks", "externalMarks", "totalMarks"):
            row.pop(field)
    rows[0][key] = 0
    rows[1][key] = 25
    page = pages(payload)[0]
    assert heading in page
    for other in {"INT.", "EXT.", "TOTAL"} - {heading}:
        assert other not in page
    # A real zero remains visible in a column retained for the whole exam.
    assert re.search(r"Mathematics\s+0\s+F", page)


@pytest.mark.parametrize("as_response", [False, True])
def test_service_returns_downloadable_pdf(monkeypatch, as_response):
    async def found(_app, _roll):
        return JSONResponse(content=PAYLOAD) if as_response else PAYLOAD
    monkeypatch.setattr(getAllResultPDFService, "fetch_all_results", found)
    response = asyncio.run(getAllResultPDFService.fetch_all_results_pdf(None, "22XX1A0501"))
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="All-Results-22XX1A0501.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert len(PdfReader(BytesIO(response.body)).pages) == 4


@pytest.mark.parametrize("status_code", [202, 404, 429, 503])
def test_service_preserves_lookup_status_and_headers(monkeypatch, status_code):
    pending = JSONResponse(status_code=status_code, content={"message": "Try again."}, headers={"Retry-After": "30"})
    async def lookup(_app, _roll):
        return pending
    monkeypatch.setattr(getAllResultPDFService, "fetch_all_results", lookup)
    assert asyncio.run(getAllResultPDFService.fetch_all_results_pdf(None, "22XX1A0501")) is pending


def test_empty_history_returns_json_instead_of_blank_pdf(monkeypatch):
    async def empty(_app, _roll):
        return {"details": PAYLOAD["details"], "results": []}
    monkeypatch.setattr(getAllResultPDFService, "fetch_all_results", empty)
    response = asyncio.run(getAllResultPDFService.fetch_all_results_pdf(None, "22XX1A0501"))
    assert response.status_code == 404
    assert response.media_type == "application/json"


def test_exam_without_subjects_still_has_a_memo():
    payload = copy.deepcopy(PAYLOAD)
    payload["results"][0]["exams"][0]["subjects"] = []
    result = pages(payload)
    assert len(result) == 4
    assert "No subjects recorded for this exam." in result[0]


def test_download_route_validates_roll_and_advertises_pdf(monkeypatch):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from api import routes

    async def found(_app, roll):
        assert roll == "22XX1A0501"
        return PAYLOAD

    monkeypatch.setattr(getAllResultPDFService, "fetch_all_results", found)
    monkeypatch.setattr(routes, "router", APIRouter())
    app = FastAPI()
    app.include_router(routes.create_routes(app))
    with TestClient(app) as client:
        response = client.get("/api/getAllResultPDF", params={"rollNumber": "22xx1a0501"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert len(PdfReader(BytesIO(response.content)).pages) == 4
        assert client.get("/api/getAllResultPDF", params={"rollNumber": "short"}).status_code == 422
        assert client.get("/api/getAllResultPDF", params={"rollNumber": "22XX1A050!"}).status_code == 400
        responses = client.get("/openapi.json").json()["paths"]["/api/getAllResultPDF"]["get"]["responses"]
        assert "application/pdf" in responses["200"]["content"]
