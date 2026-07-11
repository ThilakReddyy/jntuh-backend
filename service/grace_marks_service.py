import hmac
import json
import os
import uuid

from fastapi import UploadFile, status
from fastapi.responses import JSONResponse
from starlette.responses import Response

from config.settings import (
    GRACE_MARKS_ADMIN_KEY,
    GRACE_MARKS_PROOF_ALLOWED_TYPES,
    GRACE_MARKS_PROOF_MAX_BYTES,
)
from config.connection import prismaConnection
from database.models import GraceMarksPayload, ProofStatusUpdate, studentBacklogs
from database.operations import (
    check_4_2_semester,
    get_details,
    get_grace_marks_proof_by_id,
    get_latest_mark_for_subject,
    get_pending_grace_marks_proofs,
    list_grace_marks_proofs,
    save_grace_marks_proof,
    update_grace_marks_proof_status,
    upsert_grace_mark,
)
from utils.caching import invalidate_all_cache
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
    return (
        "".join(c if c.isalnum() or c in (".", "-", "_") else "_" for c in base)[:128]
        or "proof"
    )


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


def _serialize_proof(row) -> dict:
    return {
        "id": row.id,
        "rollNumber": row.rollNumber,
        "originalFilename": row.originalFilename,
        "contentType": row.contentType,
        "fileSize": row.fileSize,
        "status": row.status,
        "uploadedAt": row.uploadedAt.isoformat(),
        "updatedAt": row.updatedAt.isoformat(),
    }


async def get_proof_with_backlogs(app, proof_id: str, admin_key):
    """Single proof view: row metadata + 1-hour presigned GET URL + the student's backlog payload."""

    if not admin_key or not hmac.compare_digest(admin_key, GRACE_MARKS_ADMIN_KEY or ""):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "failure", "message": "Invalid admin key."},
        )
    row = await get_grace_marks_proof_by_id(proof_id)
    if not row:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "status": "failure",
                "message": "Grace-marks proof not found.",
            },
        )

    from service.getBacklogsService import fetch_backlogs

    download_url = await generate_get_url(row.s3Key)
    backlogs = await fetch_backlogs(app, row.rollNumber)

    if isinstance(backlogs, Response):
        backlogs = json.loads(backlogs.body)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            **_serialize_proof(row),
            "downloadUrl": download_url,
            "backlogs": backlogs,
        },
    )


async def apply_grace_marks(app, payload: GraceMarksPayload):
    """Insert one grace-marks mark row per subject in the payload.

    All-or-nothing: every (rollNumber, subjectCode) pair is resolved against
    the DB before any insert runs. If the student is unknown, any subject is
    unknown, or any subject has no prior mark to anchor `semesterCode` /
    `examCode` from, the request fails with 404 and nothing is written. On
    success the student's read caches are invalidated so the next read shows
    the new grace rows immediately.
    """
    roll_no = payload.rollNumber.strip().upper()
    if len(roll_no) != 10 or not roll_no.isalnum():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "failure",
                "message": "Invalid roll number. It should be 10 alphanumeric characters.",
            },
        )

    if not payload.marks:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "failure", "message": "marks array is empty."},
        )

    student = await prismaConnection.prisma.student.find_unique(
        where={"rollNumber": roll_no}
    )
    if not student:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"status": "failure", "message": "Roll number not found."},
        )

    resolved = []
    for entry in payload.marks:
        subject = await prismaConnection.prisma.subject.find_unique(
            where={"subjectCode": entry.subjectCode}
        )
        if not subject:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "status": "failure",
                    "message": f"Subject not found: {entry.subjectCode}",
                },
            )

        latest = await get_latest_mark_for_subject(student.id, subject.id)
        if not latest:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "status": "failure",
                    "message": f"No existing mark for subject {entry.subjectCode} to anchor grace insert.",
                },
            )

        resolved.append((subject.id, latest.semesterCode, latest.examCode, entry))

    try:
        for subject_id, semester_code, exam_code, entry in resolved:
            await upsert_grace_mark(
                student_id=student.id,
                subject_id=subject_id,
                semester_code=semester_code,
                exam_code=exam_code,
                internal_marks=str(entry.internalMarks),
                external_marks=str(entry.externalMarks),
                total_marks=str(entry.totalMarks),
                grades=entry.grades,
                credits=float(entry.credits),
            )
    except Exception as e:
        database_logger.error(f"Failed to insert grace marks for {roll_no}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failure",
                "message": "Failed to record grace marks. Please try again.",
            },
        )

    invalidate_all_cache(roll_no)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "success",
            "rollNumber": roll_no,
            "inserted": len(resolved),
        },
    )


async def update_proof_status(app, proof_id: str, payload: ProofStatusUpdate):
    """Set a grace-marks proof's review status to `approved` or `rejected`.

    Returns 404 when the id is unknown. Pydantic enforces the status enum, so
    invalid values are rejected by FastAPI before this function runs.
    """
    row = await get_grace_marks_proof_by_id(proof_id)
    if not row:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "status": "failure",
                "message": "Grace-marks proof not found.",
            },
        )

    try:
        updated = await update_grace_marks_proof_status(proof_id, payload.status)
    except Exception as e:
        database_logger.error(
            f"Failed to update grace-marks proof status for {proof_id}: {e}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failure",
                "message": "Failed to update status. Please try again.",
            },
        )

    if not updated:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "status": "failure",
                "message": "Grace-marks proof not found.",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "success",
            "id": updated.id,
            "rollNumber": updated.rollNumber,
            "newStatus": updated.status,
            "updatedAt": updated.updatedAt.isoformat(),
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
    if not admin_key or not hmac.compare_digest(admin_key, GRACE_MARKS_ADMIN_KEY or ""):
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
