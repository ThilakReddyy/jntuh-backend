"""Async S3 client used by the grace-marks proof upload path.

`S3_ENDPOINT_URL` lets local dev point at the MinIO sidecar in docker-compose;
leave it unset in prod so aioboto3 talks to real S3. `S3_PUBLIC_URL_BASE` is
the URL the frontend uses to fetch the object back — left blank we derive the
standard virtual-host URL.

When `S3_ENDPOINT_URL` is set (i.e. local dev) we lazily create the bucket on
first use so a fresh MinIO container Just Works. Against real AWS the bucket
must be pre-provisioned.
"""

from typing import Any, AsyncContextManager, cast

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    S3_BUCKET_NAME,
    S3_ENDPOINT_URL,
    S3_PUBLIC_URL_BASE,
)
from utils.logger import logger

_session = aioboto3.Session()
_s3_config = Config(
    signature_version="s3v4",
    s3={"addressing_style": "path" if S3_ENDPOINT_URL else "virtual"},
)


def _client_kwargs() -> dict:
    return {
        "endpoint_url": S3_ENDPOINT_URL,
        "region_name": AWS_REGION,
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        "config": _s3_config,
    }


async def _ensure_bucket(s3) -> None:
    if not S3_ENDPOINT_URL:
        return
    try:
        await s3.head_bucket(Bucket=S3_BUCKET_NAME)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchBucket", "NotFound"):
            await s3.create_bucket(Bucket=S3_BUCKET_NAME)
            logger.info(f"Created local S3 bucket: {S3_BUCKET_NAME}")
            return
        raise


async def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    client_ctx = cast(
        AsyncContextManager[Any], _session.client("s3", **_client_kwargs())
    )
    async with client_ctx as s3:
        await _ensure_bucket(s3)
        await s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    if S3_PUBLIC_URL_BASE:
        return f"{S3_PUBLIC_URL_BASE.rstrip('/')}/{key}"
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"


async def generate_get_url(key: str, expires_in: int = 3600) -> str:
    """Return a presigned GET URL for `key` valid for `expires_in` seconds.

    Use this for any caller that needs read access to a private object — the
    frontend gets a time-bound URL it can fetch directly without the bucket
    being public.
    """
    client_ctx = cast(
        AsyncContextManager[Any], _session.client("s3", **_client_kwargs())
    )
    async with client_ctx as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )


async def generate_get_urls(
    keys: list[str], expires_in: int = 3600
) -> dict[str, str]:
    """Batch-sign multiple keys inside one client context.

    Per-row `generate_get_url` would open a fresh client for every key; this
    variant amortizes that setup across the whole list.
    """
    if not keys:
        return {}
    client_ctx = cast(
        AsyncContextManager[Any], _session.client("s3", **_client_kwargs())
    )
    async with client_ctx as s3:
        return {
            k: await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET_NAME, "Key": k},
                ExpiresIn=expires_in,
            )
            for k in keys
        }
