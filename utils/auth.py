import hmac

from fastapi import Header, HTTPException, status

from config.settings import GRACE_MARKS_ADMIN_KEY


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> None:
    if not x_api_key or not hmac.compare_digest(
        x_api_key, GRACE_MARKS_ADMIN_KEY or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "failure", "message": "Invalid API key."},
        )
