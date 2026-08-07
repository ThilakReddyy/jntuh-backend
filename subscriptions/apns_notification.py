import asyncio
import base64
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from config.settings import (
    APNS_BUNDLE_ID,
    APNS_KEY_ID,
    APNS_PRIVATE_KEY,
    APNS_PRIVATE_KEY_PATH,
    APNS_TEAM_ID,
)
from database.operations import (
    delete_apns_devices,
    delete_apns_device_for_device,
    delete_result_device_subscriptions,
    delete_result_device_subscriptions_for_device,
    get_apns_devices,
    get_result_device_subscriptions,
)
from utils.logger import logger


_provider_token_lock = Lock()
_cached_provider_token: tuple[str, int] | None = None
_INVALID_TOKEN_REASONS = {
    "BadDeviceToken",
    "DeviceTokenNotForTopic",
    "Unregistered",
}


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _private_key_bytes() -> bytes:
    if APNS_PRIVATE_KEY:
        return APNS_PRIVATE_KEY.replace("\\n", "\n").encode("utf-8")
    if APNS_PRIVATE_KEY_PATH:
        return Path(APNS_PRIVATE_KEY_PATH).expanduser().read_bytes()
    raise RuntimeError("APNS_PRIVATE_KEY or APNS_PRIVATE_KEY_PATH is not configured")


def _create_provider_token(now: int | None = None) -> str:
    if not APNS_KEY_ID or not APNS_TEAM_ID:
        raise RuntimeError("APNS_KEY_ID and APNS_TEAM_ID must be configured")

    issued_at = now or int(time.time())
    header = _base64url(
        json.dumps({"alg": "ES256", "kid": APNS_KEY_ID}, separators=(",", ":")).encode()
    )
    claims = _base64url(
        json.dumps(
            {"iss": APNS_TEAM_ID, "iat": issued_at}, separators=(",", ":")
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    private_key = serialization.load_pem_private_key(
        _private_key_bytes(), password=None
    )
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise RuntimeError("APNs authentication key is not an EC private key")
    der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    signature = _base64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"{header}.{claims}.{signature}"


def _provider_token() -> str:
    global _cached_provider_token
    now = int(time.time())
    with _provider_token_lock:
        if _cached_provider_token and now - _cached_provider_token[1] < 50 * 60:
            return _cached_provider_token[0]
        token = _create_provider_token(now)
        _cached_provider_token = (token, now)
        return token


def _build_result_payload(exam: Mapping[str, Any]) -> dict[str, Any]:
    title = str(exam.get("title") or "A new JNTUH result is available").strip()
    link = str(
        exam.get("link") or "https://jntuhconnect.dhethi.com/notifications"
    ).strip()
    return {
        "aps": {
            "alert": {"title": "JNTUH Results Released", "body": title},
            "sound": "default",
        },
        "destination": "updates",
        "link": link,
    }


def _build_student_result_payload(roll_number: str) -> dict[str, Any]:
    return {
        "aps": {
            "alert": {
                "title": "Your JNTUH results were updated",
                "body": f"New result records are available for {roll_number}.",
            },
            "sound": "default",
        },
        "destination": "student-result",
        "rollNumber": roll_number,
    }


async def _send_notification(
    client: httpx.AsyncClient,
    device_token: str,
    environment: str,
    payload: Mapping[str, Any],
) -> tuple[bool, str | None]:
    host = (
        "https://api.development.push.apple.com"
        if environment == "sandbox"
        else "https://api.push.apple.com"
    )
    response = await client.post(
        f"{host}/3/device/{device_token}",
        headers={
            "authorization": f"bearer {_provider_token()}",
            "apns-topic": APNS_BUNDLE_ID,
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        json=payload,
    )
    if response.status_code == 200:
        return True, None
    try:
        reason = str(response.json().get("reason") or f"HTTP {response.status_code}")
    except (ValueError, AttributeError):
        reason = f"HTTP {response.status_code}"
    return False, reason


async def _deliver_many(
    records, payload: Mapping[str, Any]
) -> tuple[int, list[str], list[str]]:
    if not records:
        return 0, [], []
    semaphore = asyncio.Semaphore(20)
    invalid_ids: list[str] = []
    invalid_device_ids: list[str] = []
    success_count = 0

    async with httpx.AsyncClient(http2=True, timeout=15) as client:

        async def deliver(record) -> None:
            nonlocal success_count
            async with semaphore:
                try:
                    success, reason = await _send_notification(
                        client,
                        record.deviceToken,
                        getattr(record, "environment", None) or "production",
                        payload,
                    )
                    if success:
                        success_count += 1
                    else:
                        if reason in _INVALID_TOKEN_REASONS:
                            invalid_ids.append(record.id)
                            invalid_device_ids.append(record.deviceId)
                        logger.error(f"APNs notification failed: {reason}")
                except Exception as error:
                    logger.error(f"APNs notification request failed: {error}")

        await asyncio.gather(*(deliver(record) for record in records))
    return success_count, invalid_ids, invalid_device_ids


async def notify_ios_student_result_updated(roll_number: str) -> None:
    subscriptions = await get_result_device_subscriptions(roll_number, platform="ios")
    success_count, invalid_ids, invalid_device_ids = await _deliver_many(
        subscriptions, _build_student_result_payload(roll_number)
    )
    await delete_result_device_subscriptions(invalid_ids)
    for device_id in set(invalid_device_ids):
        await delete_apns_device_for_device(device_id)
    logger.info(
        f"APNs student result notifications complete: {success_count} sent, "
        f"{len(invalid_ids)} invalid tokens removed"
    )


async def broadcast_ios_result_notifications(
    exams: Sequence[Mapping[str, Any]],
) -> None:
    try:
        devices = await get_apns_devices()
        print(devices)
        for exam in exams:
            success_count, invalid_ids, invalid_device_ids = await _deliver_many(
                devices, _build_result_payload(exam)
            )
            await delete_apns_devices(invalid_ids)
            for device_id in set(invalid_device_ids):
                await delete_result_device_subscriptions_for_device(device_id)
            if invalid_ids:
                invalid = set(invalid_ids)
                devices = [device for device in devices if device.id not in invalid]
            logger.info(
                f"APNs result notifications complete: {success_count} sent, "
                f"{len(invalid_ids)} invalid tokens removed"
            )
    except Exception as error:
        logger.error(f"APNs result notification broadcast failed: {error}")
