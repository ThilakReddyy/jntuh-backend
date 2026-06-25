import hmac
import os
import uuid

from fastapi import UploadFile, status
from fastapi.responses import JSONResponse

from config.settings import (
    GRACE_MARKS_ADMIN_KEY,
    GRACE_MARKS_PROOF_ALLOWED_TYPES,
    GRACE_MARKS_PROOF_MAX_BYTES,
)
from database.models import studentBacklogs
from database.operations import (
    check_4_2_semester,
    get_details,
    get_pending_grace_marks_proofs,
    save_grace_marks_proof,
)
from utils.logger import database_logger, logger
from utils.s3 import generate_get_url, generate_get_urls, upload_bytes


async def evaluate_eligibility(roll_no: str):
    """Pure eligibility check used by both the GET eligibility route and the POST proof upload.

    Returns a `(eligible, status_code, payload)` tuple. The status code matches
    what `check_eligibility` historically returned for the same input shape, so
    HTTP callers can pass the code straight through to `JSONResponse`.
    """
    if roll_no[5] != "A" and roll_no[5] != "R":
        return (
            False,
            status.HTTP_200_OK,
            {
                "status": "failure",
                "message": "This Feature is currently only available for Btech and Bpharm Students",
            },
        )
    if not await check_4_2_semester(roll_no):
        return (
            False,
            status.HTTP_200_OK,
            {
                "status": "failure",
                "message": "Your 4-2 semester marks haven't yet synced",
            },
        )

    response = await get_details(roll_no)
    if not response:
        return (
            False,
            status.HTTP_404_NOT_FOUND,
            {
                "status": "failure",
                "message": "Unable to find your roll number",
            },
        )

    _, marks = response
    backlogs = studentBacklogs(marks, False)
    if backlogs["totalBacklogs"] == 0:
        return (
            False,
            status.HTTP_406_NOT_ACCEPTABLE,
            {
                "status": "failure",
                "message": "You have passed all the exams not applicable to you",
            },
        )

    return True, status.HTTP_200_OK, backlogs


async def check_eligibility(app, roll_no: str):
    """Determine whether a final-year student is eligible for the JNTUH grace-marks scheme.

    Two preconditions must hold: (1) the 5th char of the roll number must be
    `A` (B.Tech) or `R` (B.Pharm) — other degrees are rejected outright; (2)
    the student's 4-2 (final-semester) marks must already be synced into the
    DB. On success the response IS the backlog list (same shape as
    `fetch_backlogs`) — the frontend uses that list to render which subjects
    can be raised by grace marks.

    Response codes mirror the legacy shape: 200 success / 200 failure for
    degree+sync precondition failures, 404 when no record exists, 406 when the
    student has no backlogs.
    """
    eligible, status_code, payload = await evaluate_eligibility(roll_no)
    if eligible:
        return payload
    if status_code == status.HTTP_200_OK:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


def _sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "proof")
    return "".join(c if c.isalnum() or c in (".", "-", "_") else "_" for c in base)[
        :128
    ] or "proof"


async def upload_proof(app, roll_no: str, file: UploadFile):
    """Re-verify grace-marks eligibility, then push the uploaded sheet to S3 and record it.

    Eligibility is checked with the same helper the GET route uses, so a roll
    number that is rejected by `check_eligibility` is rejected here with the
    identical status code and payload. On success we store the object under
    `grace-marks-proofs/<rollNo>/<uuid>-<filename>` and persist its S3 key,
    URL, content type, and size in the `GraceMarksProof` table.
    """
    eligible, status_code, payload = await evaluate_eligibility(roll_no)
    if not eligible:
        return JSONResponse(status_code=status_code, content=payload)

    content_type = (file.content_type or "").lower()
    if content_type not in GRACE_MARKS_PROOF_ALLOWED_TYPES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "failure",
                "message": "Only PDF or image (PNG/JPEG) uploads are accepted.",
            },
        )

    data = await file.read()
    if len(data) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "failure", "message": "Uploaded file is empty."},
        )
    if len(data) > GRACE_MARKS_PROOF_MAX_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "status": "failure",
                "message": "File exceeds the 5MB upload limit.",
            },
        )

    filename = _sanitize_filename(file.filename or "proof")
    key = f"grace-marks-proofs/{roll_no}/{uuid.uuid4()}-{filename}"

    try:
        s3_url = await upload_bytes(key, data, content_type)
    except Exception:
        logger.exception(f"S3 upload failed for {roll_no}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "status": "failure",
                "message": "Unable to store the uploaded file. Please try again.",
            },
        )

    try:
        record = await save_grace_marks_proof(
            roll_number=roll_no,
            s3_key=key,
            s3_url=s3_url,
            filename=filename,
            content_type=content_type,
            size=len(data),
        )
    except Exception as e:
        database_logger.error(f"Failed to persist grace-marks proof for {roll_no}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failure",
                "message": "File uploaded but could not be recorded. Please try again.",
            },
        )

    download_url = await generate_get_url(key)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "success",
            "rollNumber": roll_no,
            "downloadUrl": download_url,
            "uploadedAt": record.uploadedAt.isoformat(),
        },
    )


async def list_pending_proofs(app, admin_key: str | None):
    """Admin-only listing of the oldest 10 pending proofs, each with a signed GET URL.

    Two rejection paths, both → 401:
      - `X-Admin-Key` header missing (admin_key is None or empty).
      - Header present but does not match `GRACE_MARKS_ADMIN_KEY`.
    `hmac.compare_digest` is constant-time so a bad key can't be inferred from
    response timing.
    """
    if not admin_key or not hmac.compare_digest(
        admin_key, GRACE_MARKS_ADMIN_KEY or ""
    ):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "failure", "message": "Invalid admin key."},
        )

    rows = await get_pending_grace_marks_proofs()
    signed = await generate_get_urls([r.s3Key for r in rows])

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "count": len(rows),
            "proofs": [
                {
                    "id": r.id,
                    "rollNumber": r.rollNumber,
                    "originalFilename": r.originalFilename,
                    "contentType": r.contentType,
                    "fileSize": r.fileSize,
                    "status": r.status,
                    "uploadedAt": r.uploadedAt.isoformat(),
                    "updatedAt": r.updatedAt.isoformat(),
                    "downloadUrl": signed[r.s3Key],
                }
                for r in rows
            ],
        },
    )
