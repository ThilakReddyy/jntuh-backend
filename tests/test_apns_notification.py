import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from database.models import APNSDeviceRegistrationPayload, ResultDeviceSubscriptionPayload
from subscriptions import apns_notification


def _decode_segment(segment: str) -> dict:
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + padding))


def test_apns_provider_token_contains_key_and_team_metadata():
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    with (
        patch.object(apns_notification, "APNS_KEY_ID", "KEY123"),
        patch.object(apns_notification, "APNS_TEAM_ID", "TEAM123"),
        patch.object(apns_notification, "APNS_PRIVATE_KEY", pem),
    ):
        token = apns_notification._create_provider_token(now=1_700_000_000)

    header, claims, signature = token.split(".")
    assert _decode_segment(header) == {"alg": "ES256", "kid": "KEY123"}
    assert _decode_segment(claims) == {"iss": "TEAM123", "iat": 1_700_000_000}
    assert len(base64.urlsafe_b64decode(signature + "==")) == 64


def test_apns_payloads_match_ios_navigation_contract():
    release = apns_notification._build_result_payload(
        {"title": "B.Tech results", "link": "https://results.jntuh.ac.in/result"}
    )
    student = apns_notification._build_student_result_payload("20J21A0101")

    assert release["destination"] == "updates"
    assert release["link"] == "https://results.jntuh.ac.in/result"
    assert release["aps"]["alert"]["body"] == "B.Tech results"
    assert student["destination"] == "student-result"
    assert student["rollNumber"] == "20J21A0101"


def test_apns_request_uses_environment_specific_host():
    response = SimpleNamespace(status_code=200)
    client = SimpleNamespace(post=AsyncMock(return_value=response))

    with patch.object(apns_notification, "_provider_token", return_value="provider-token"):
        result = asyncio.run(
            apns_notification._send_notification(
                client, "ab" * 32, "sandbox", {"aps": {"alert": "Test"}}
            )
        )

    assert result == (True, None)
    request = client.post.await_args
    assert request.args[0] == f"https://api.development.push.apple.com/3/device/{'ab' * 32}"
    assert request.kwargs["headers"]["apns-topic"] == "com.dhethi.jntuhconnect.ios"
    assert request.kwargs["headers"]["apns-push-type"] == "alert"


def test_ios_subscription_requires_apns_environment():
    try:
        ResultDeviceSubscriptionPayload(
            deviceId="550e8400-e29b-41d4-a716-446655440000",
            deviceToken="ab" * 32,
            rollNumber="20J21A0101",
            platform="ios",
        )
        assert False, "Expected validation failure"
    except ValueError:
        pass

    registration = APNSDeviceRegistrationPayload(
        deviceId="550e8400-e29b-41d4-a716-446655440000",
        deviceToken="AB" * 32,
        environment="production",
    )
    assert registration.deviceToken == "ab" * 32
