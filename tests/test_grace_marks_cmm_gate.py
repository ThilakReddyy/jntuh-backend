import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import UploadFile


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


# Keep this unit test independent of the optional local AWS client install.
async def _unused_s3(*_args, **_kwargs):
    raise AssertionError("unexpected unmocked S3 call")


s3_stub = ModuleType("utils.s3")
s3_stub.generate_get_url = _unused_s3
s3_stub.generate_get_urls = _unused_s3
s3_stub.upload_bytes = _unused_s3
sys.modules.setdefault("utils.s3", s3_stub)

from service import grace_marks_service  # noqa: E402


def _upload() -> UploadFile:
    from io import BytesIO

    return UploadFile(
        filename="memo.jpg",
        file=BytesIO(b"candidate"),
        headers={"content-type": "image/jpeg"},
    )


def _body(response) -> dict:
    return json.loads(response.body)


def _proof(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="proof-id",
        rollNumber="22XX1A0501",
        status=status,
        updatedAt=datetime.now(timezone.utc),
    )


def test_approving_proof_sends_student_result_fcm(monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(
        grace_marks_service,
        "get_grace_marks_proof_by_id",
        AsyncMock(return_value=_proof("pending")),
    )
    monkeypatch.setattr(
        grace_marks_service,
        "update_grace_marks_proof_status",
        AsyncMock(return_value=_proof("approved")),
    )
    monkeypatch.setattr(grace_marks_service, "_notify_student_result_updated", notify)

    response = asyncio.run(
        grace_marks_service.update_proof_status(
            None,
            "proof-id",
            grace_marks_service.ProofStatusUpdate(status="approved"),
        )
    )

    assert response.status_code == 200
    notify.assert_awaited_once_with("22XX1A0501")


def test_repeated_approval_does_not_send_duplicate_fcm(monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(
        grace_marks_service,
        "get_grace_marks_proof_by_id",
        AsyncMock(return_value=_proof("approved")),
    )
    monkeypatch.setattr(
        grace_marks_service,
        "update_grace_marks_proof_status",
        AsyncMock(return_value=_proof("approved")),
    )
    monkeypatch.setattr(grace_marks_service, "_notify_student_result_updated", notify)

    response = asyncio.run(
        grace_marks_service.update_proof_status(
            None,
            "proof-id",
            grace_marks_service.ProofStatusUpdate(status="approved"),
        )
    )

    assert response.status_code == 200
    notify.assert_not_awaited()


def test_invalid_document_is_not_uploaded_or_saved(monkeypatch):
    calls = {"upload": 0, "save": 0}

    async def eligible(_roll_no):
        return True, 200, {}

    async def classify(_data, _content_type):
        return SimpleNamespace(classification="not_cmm", is_cmm=False)

    async def upload(*_args, **_kwargs):
        calls["upload"] += 1

    async def save(*_args, **_kwargs):
        calls["save"] += 1

    monkeypatch.setattr(grace_marks_service, "evaluate_eligibility", eligible)
    monkeypatch.setattr(grace_marks_service, "classify_cmm_document", classify)
    monkeypatch.setattr(grace_marks_service, "upload_bytes", upload)
    monkeypatch.setattr(grace_marks_service, "save_grace_marks_proof", save)

    response = asyncio.run(
        grace_marks_service.upload_proof(None, "22XX1A0501", _upload())
    )

    assert response.status_code == 422
    assert _body(response)["classification"] == "not_cmm"
    assert calls == {"upload": 0, "save": 0}


def test_uncertain_document_is_not_uploaded_or_saved(monkeypatch):
    async def eligible(_roll_no):
        return True, 200, {}

    async def classify(_data, _content_type):
        return SimpleNamespace(classification="uncertain", is_cmm=False)

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("storage must not run for an uncertain document")

    monkeypatch.setattr(grace_marks_service, "evaluate_eligibility", eligible)
    monkeypatch.setattr(grace_marks_service, "classify_cmm_document", classify)
    monkeypatch.setattr(grace_marks_service, "upload_bytes", unexpected)
    monkeypatch.setattr(grace_marks_service, "save_grace_marks_proof", unexpected)

    response = asyncio.run(
        grace_marks_service.upload_proof(None, "22XX1A0501", _upload())
    )

    assert response.status_code == 422
    assert _body(response)["classification"] == "uncertain"


def test_confirmed_cmm_is_uploaded_then_saved(monkeypatch):
    calls = []

    async def eligible(_roll_no):
        return True, 200, {}

    async def classify(_data, _content_type):
        calls.append("classify")
        return SimpleNamespace(classification="cmm", is_cmm=True)

    async def upload(*_args, **_kwargs):
        calls.append("upload")
        return "s3://proof"

    async def save(*_args, **_kwargs):
        calls.append("save")
        return SimpleNamespace(uploadedAt=SimpleNamespace(isoformat=lambda: "now"))

    async def get_url(_key):
        return "https://example.test/proof"

    monkeypatch.setattr(grace_marks_service, "evaluate_eligibility", eligible)
    monkeypatch.setattr(grace_marks_service, "classify_cmm_document", classify)
    monkeypatch.setattr(grace_marks_service, "upload_bytes", upload)
    monkeypatch.setattr(grace_marks_service, "save_grace_marks_proof", save)
    monkeypatch.setattr(grace_marks_service, "generate_get_url", get_url)

    response = asyncio.run(
        grace_marks_service.upload_proof(None, "22XX1A0501", _upload())
    )

    assert response.status_code == 200
    assert calls == ["classify", "upload", "save"]
