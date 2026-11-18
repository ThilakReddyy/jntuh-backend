import asyncio
import base64
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock

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


def _response(choice="cmm", probabilities=None, sample_probability=0.01):
    probabilities = probabilities or {"cmm": 0.98, "not_cmm": 0.01, "uncertain": 0.01}
    return {
        "answers": {
            "classification": {
                "type": "choice",
                "choice": choice,
                "confidence": probabilities[choice],
                "probabilities": probabilities,
            },
            "sample_or_invalid": {
                "type": "noul",
                "noul": sample_probability,
                "confidence": max(sample_probability, 1 - sample_probability),
            },
        },
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
        (_response(sample_probability=0.99), "not_cmm"),
        (_response(sample_probability=0.2), "uncertain"),
        (_response(sample_probability=0.5), "not_cmm"),
        (
            _response(
                probabilities={"cmm": 0.9, "not_cmm": 0.05, "uncertain": 0.05},
                sample_probability=0.1,
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
        {"answers": {"classification": _response()["answers"]["classification"]}},
    ],
)
def test_missing_answers_fail_closed(payload):
    with pytest.raises(ValidationError):
        classifier._parse_decision_response(payload)


@pytest.mark.parametrize(
    "field,value",
    [("type", "choice"), ("noul", float("inf")), ("noul", 0.0), ("confidence", 0.1)],
)
def test_invalid_sample_answer_fails_closed(field, value):
    payload = _response()
    payload["answers"]["sample_or_invalid"][field] = value
    with pytest.raises(ValidationError):
        classifier._parse_decision_response(payload)


@pytest.mark.parametrize(
    "reference_suffix,candidate_mime",
    [(".jpg", "application/pdf"), (".pdf", "image/png")],
)
def test_classifier_uses_decisions_and_serializes_documents(
    monkeypatch, tmp_path, reference_suffix, candidate_mime
):
    # Exercise the real SDK request serialization and response parsing without network I/O.
    import httpx
    from google import genai

    reference = tmp_path / ("reference" + reference_suffix)
    reference.write_bytes(b"reference")
    monkeypatch.setattr(classifier, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(classifier, "GEMINI_MODEL", "gemini-decision-1")
    monkeypatch.setattr(classifier, "CMM_REFERENCE_PATH", reference)
    captured = []

    def handle(request, **_kwargs):
        import json

        captured.append((request, json.loads(request.content)))
        return httpx.Response(200, json=_response(), request=request)

    # GAOS uses its own HTTP client, so replace its send method at the transport boundary.
    with genai.Client(
        api_key="test-key", http_options={"api_version": "v1beta"}
    ) as client:
        monkeypatch.setattr(client.decisions.sdk_configuration.client, "send", handle)
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        monkeypatch.setattr(classifier.genai, "Client", factory)
        result = asyncio.run(
            classifier.classify_cmm_document(b"candidate", candidate_mime)
        )

    assert result.is_cmm
    factory.assert_called_once_with(
        api_key="test-key", http_options={"api_version": "v1beta"}
    )
    request, body = captured[0]
    assert request.url.path == "/v1beta/decisions"
    assert body["model"] == "gemini-decision-1"
    assert body["questions"]["classification"]["type"] == "choice"
    assert body["questions"]["sample_or_invalid"]["type"] == "noul"
    reference_block, candidate_block = body["input"][1], body["input"][3]
    for block, data, mime in (
        (
            reference_block,
            b"reference",
            "application/pdf" if reference_suffix == ".pdf" else "image/jpeg",
        ),
        (candidate_block, b"candidate", candidate_mime),
    ):
        assert base64.b64decode(block["data"]) == data
        assert block["mime_type"] == mime
        assert block["type"] == ("document" if mime == "application/pdf" else "image")
    assert "generationConfig" not in body


@pytest.mark.parametrize(
    "failure", ["key", "model", "reference", "reference_type", "size", "mime"]
)
def test_configuration_and_input_fail_before_provider_call(
    monkeypatch, tmp_path, failure
):
    reference = tmp_path / (
        "reference.txt" if failure == "reference_type" else "reference.jpg"
    )
    if failure != "reference":
        reference.write_bytes(b"reference")
    monkeypatch.setattr(
        classifier, "GEMINI_API_KEY", None if failure == "key" else "test-key"
    )
    monkeypatch.setattr(
        classifier,
        "GEMINI_MODEL",
        "gemini-3.5-flash" if failure == "model" else "gemini-decision-1",
    )
    monkeypatch.setattr(classifier, "CMM_REFERENCE_PATH", reference)
    if failure == "size":
        monkeypatch.setattr(classifier, "MAX_INLINE_BYTES", 1)
    factory = MagicMock(side_effect=AssertionError("provider must not run"))
    monkeypatch.setattr(classifier.genai, "Client", factory)
    with pytest.raises((classifier.CMMClassifierConfigurationError, ValueError)):
        asyncio.run(
            classifier.classify_cmm_document(
                b"candidate", "text/plain" if failure == "mime" else "image/jpeg"
            )
        )
    factory.assert_not_called()
