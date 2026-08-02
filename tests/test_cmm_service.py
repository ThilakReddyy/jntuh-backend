import asyncio
import json
import os
import sys
from pathlib import Path

from fastapi import status
from fastapi.responses import JSONResponse


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for name, value in {
    "RABBITMQ_URL": "amqp://guest:guest@localhost/",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/jntuh",
    "QUEUE_NAME": "test",
    "REDIS_URL": "redis://localhost:6379/0",
    "VAPID_PUBLIC_KEY": "test",
    "VAPID_PRIVATE_KEY": "test",
    "TELEGRAM_TOKEN": "test",
    "TELEGRAM_CHAT_ID": "test",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1",
    "S3_BUCKET_NAME": "test",
    "GRACE_MARKS_ADMIN_KEY": "test",
}.items():
    os.environ.setdefault(name, value)

from service import getCMMService  # noqa: E402
from service.cmm_pdf import generate_cmm_pdf  # noqa: E402


PAYLOAD = {
    "details": {
        "name": "Test Student",
        "rollNumber": "22XX1A0501",
        "collegeCode": "XX",
        "fatherName": "Test Parent",
        "branch": "Computer Science and Engineering",
    },
    "results": {
        "semesters": [
            {
                "semester": "1-1",
                "subjects": [
                    {
                        "subjectName": "Mathematics",
                        "grades": "A",
                        "credits": 4,
                    }
                ],
            }
        ],
        "CGPA": "8.00",
        "credits": 4,
    },
}


def test_generate_cmm_pdf_returns_a_pdf_document():
    pdf = generate_cmm_pdf(PAYLOAD)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000
    assert b"https://jntuhconnect.dhethi.com" in pdf


def test_fetch_cmm_returns_downloadable_pdf(monkeypatch):
    async def result_found(_app, _roll_number):
        return PAYLOAD

    monkeypatch.setattr(getCMMService, "fetch_results", result_found)
    response = asyncio.run(getCMMService.fetch_cmm(None, "22XX1A0501"))

    assert response.status_code == status.HTTP_200_OK
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")
    assert response.headers["content-disposition"] == (
        'attachment; filename="CMM-22XX1A0501.pdf"'
    )
    assert response.headers["cache-control"] == "private, no-store"


def test_fetch_cmm_preserves_pending_lookup_response(monkeypatch):
    pending = JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "success", "message": "Your roll number has been queued."},
    )

    async def result_pending(_app, _roll_number):
        return pending

    monkeypatch.setattr(getCMMService, "fetch_results", result_pending)
    response = asyncio.run(getCMMService.fetch_cmm(None, "22XX1A0501"))

    assert response is pending
    assert json.loads(response.body)["message"] == "Your roll number has been queued."
