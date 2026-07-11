import hmac

from fastapi import Header, HTTPException, status

from config.settings import GRACE_MARKS_ADMIN_KEY


def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key, GRACE_MARKS_ADMIN_KEY or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "failure", "message": "Invalid API key."},
        )
