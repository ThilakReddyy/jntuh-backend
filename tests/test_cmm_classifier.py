import asyncio
import base64
import os
from pathlib import Path
import sys
import json
from time import perf_counter

import httpx

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in (
    "RABBITMQ_URL",
    "DATABASE_URL",
    "QUEUE_NAME",
    "REDIS_URL",
    "VAPID_PUBLIC_KEY",
    "VAPID_PRIVATE_KEY",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "S3_BUCKET_NAME",
    "GRACE_MARKS_ADMIN_KEY",
):
    os.environ.setdefault(name, "test")

from service import cmm_classifier as classifier  # noqa: E402


def _response(choice="cmm", probabilities=None):
    probabilities = probabilities or {"cmm": 0.98, "not_cmm": 0.01, "uncertain": 0.01}
    return {
        "answers": {
            "classification": {
                "type": "choice",
                "choice": choice,
                "confidence": probabilities[choice],
                "probabilities": probabilities,
            }
        }
    }


@pytest.mark.parametrize(
    "payload, expected",
    [
        (_response(), "cmm"),
        (
            _response("not_cmm", {"cmm": 0.01, "not_cmm": 0.98, "uncertain": 0.01}),
            "not_cmm",
        ),
        (
            _response("uncertain", {"cmm": 0.1, "not_cmm": 0.1, "uncertain": 0.8}),
            "uncertain",
        ),
        (
            _response(probabilities={"cmm": 0.8, "not_cmm": 0.1, "uncertain": 0.1}),
            "uncertain",
        ),
        (
            _response(
                probabilities={"cmm": 0.9, "not_cmm": 0.05, "uncertain": 0.05},
            ),
            "cmm",
        ),
    ],
)
def test_decision_policy(payload, expected):
    result = classifier._parse_decision_response(payload)
    assert result.classification == expected
    assert result.is_cmm is (expected == "cmm")
    assert result.evidence == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "score"),
        ("choice", "unknown"),
        ("confidence", 1.1),
        ("confidence", float("nan")),
        ("confidence", "0.98"),
        ("confidence", 0.5),
        ("choice", "not_cmm"),
        ("probabilities", {"cmm": 0.98}),
        ("probabilities", {"cmm": 0.98, "not_cmm": 0.1, "uncertain": 0.1}),
        ("probabilities", {"cmm": 0.98, "not_cmm": -0.01, "uncertain": 0.03}),
    ],
)
def test_invalid_classification_fails_closed(field, value):
    payload = _response()
    payload["answers"]["classification"][field] = value
    with pytest.raises(ValidationError):
        classifier._parse_decision_response(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"answers": None},
        {"answers": {}},
        {"answers": {"classification": None}},
    ],
)
def test_missing_answers_fail_closed(payload):
    with pytest.raises(ValidationError):
        classifier._parse_decision_response(payload)


@pytest.mark.parametrize("mime", ["application/pdf", "image/jpeg", "image/png"])
def test_request_sends_only_candidate_and_reuses_client(monkeypatch, mime):
    monkeypatch.setattr(classifier, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(classifier, "GEMINI_MODEL", "gemini-decision-1")
    captured = []

    async def handle(request):
        captured.append(request)
        return httpx.Response(200, json=_response())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            for _ in range(2):
                result = await classifier.classify_cmm_document(
                    b"candidate", mime, http_client=client
                )
                assert result.is_cmm
                assert not client.is_closed

    asyncio.run(run())
    assert len(captured) == 2
    request = captured[0]
    assert str(request.url) == classifier.DECISIONS_URL
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["model"] == "gemini-decision-1"
    assert len(body["input"]) == 1
    block = body["input"][0]
    assert base64.b64decode(block["data"]) == b"candidate"
    assert block["mime_type"] == mime
    assert block["type"] == ("document" if mime == "application/pdf" else "image")
    assert list(body["questions"]) == ["classification"]
    assert "sample" in body["questions"]["classification"]["criteria"]["not_cmm"]


@pytest.mark.parametrize(
    "status,code,client_status",
    [
        (401, "verification_unavailable", 503),
        (403, "verification_unavailable", 503),
        (429, "verification_busy", 503),
        (500, "verification_provider_error", 502),
        (503, "verification_provider_error", 502),
    ],
)
def test_provider_error_is_not_retried_and_is_sanitized(
    monkeypatch, status, code, client_status
):
    monkeypatch.setattr(classifier, "GEMINI_API_KEY", "test-key")
    calls = []

    async def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "secret provider details"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(classifier.CMMVerificationError) as caught:
                await classifier.classify_cmm_document(
                    b"candidate", "image/jpeg", http_client=client
                )
            assert caught.value.code == code
            assert caught.value.status_code == client_status
            assert "secret" not in str(caught.value)

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", ["connection", "transport_timeout", "malformed_json", "invalid_schema"]
)
def test_provider_failures(monkeypatch, failure):
    monkeypatch.setattr(classifier, "GEMINI_API_KEY", "test-key")

    async def handle(request):
        if failure == "connection":
            raise httpx.ConnectError("secret", request=request)
        if failure == "transport_timeout":
            raise httpx.ReadTimeout("secret", request=request)
        if failure == "malformed_json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"answers": {}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(classifier.CMMVerificationError) as caught:
                await classifier.classify_cmm_document(
                    b"candidate", "image/jpeg", http_client=client
                )
            expected = {
                "connection": ("verification_unavailable", 503),
                "transport_timeout": ("verification_timeout", 504),
            }.get(failure, ("verification_invalid_response", 502))
            assert (caught.value.code, caught.value.status_code) == expected
            assert "secret" not in str(caught.value)

    asyncio.run(run())


def test_wall_clock_deadline_cancels_provider_without_retry(monkeypatch):
    monkeypatch.setattr(classifier, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(classifier, "CMM_VERIFICATION_TIMEOUT_SECONDS", 0.02)
    calls = []
    cancelled = []

    async def handle(request):
        calls.append(request)
        try:
            await asyncio.sleep(60)
            return httpx.Response(200, json=_response())
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            started = perf_counter()
            with pytest.raises(classifier.CMMVerificationError) as caught:
                await classifier.classify_cmm_document(
                    b"candidate", "image/jpeg", http_client=client
                )
            assert caught.value.status_code == 504
            assert caught.value.code == "verification_timeout"
            assert perf_counter() - started < 0.5

    asyncio.run(run())
    assert len(calls) == 1
    assert cancelled == [True]


@pytest.mark.parametrize("failure", ["key", "model", "size", "mime"])
def test_invalid_configuration_and_input_fail_before_provider(monkeypatch, failure):
    monkeypatch.setattr(
        classifier, "GEMINI_API_KEY", None if failure == "key" else "test-key"
    )
    monkeypatch.setattr(
        classifier,
        "GEMINI_MODEL",
        "gemini-3.5-flash" if failure == "model" else "gemini-decision-1",
    )
    if failure == "size":
        monkeypatch.setattr(classifier, "MAX_INLINE_BYTES", 1)

    async def handle(request):
        raise AssertionError("provider must not run")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(
                (classifier.CMMClassifierConfigurationError, ValueError)
            ):
                await classifier.classify_cmm_document(
                    b"candidate",
                    "text/plain" if failure == "mime" else "image/jpeg",
                    http_client=client,
                )

    asyncio.run(run())
