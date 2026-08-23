import os
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse

from config.connection import prismaConnection
from config.rateLimiter import limiter
from config.redisConnection import redisConnection
from config.settings import IS_PRODUCTION
from chatbot.errors import (
    ChatbotNotConfiguredError,
    ChatbotResponseError,
    ChatbotUpstreamError,
    ChatbotUpstreamTimeoutError,
)
from chatbot.schemas import ChatRequest, ChatResponse
from database.models import (
    APNSDeviceRegistrationPayload,
    GraceMarksPayload,
    NotificationPreferencePayload,
    ProofStatusUpdate,
    PushSub,
    ResultDeviceSubscriptionPayload,
)
from service.getAllResultService import fetch_all_results
from service.getBacklogsService import fetch_backlogs
from service.getClassResults import fetch_class_results
from service.getCMMService import fetch_cmm
from service.getRequiredCreditsService import fetch_required_credits
from service.getResultContrastService import fetch_result_contrast
from service.getResultsService import fetch_results
from service.hardrefresh import fetch_results_using_hard_refresh
from service.contentService import getCalendars, getSyllabus
from service.notificationService import (
    getLatestNotifications,
    notification,
    refreshNotification,
)
from service.jobsService import fetch_jobs
from service.subscriptionService import (
    delete_notification_preferences,
    delete_result_subscriptions,
    get_notification_preferences,
    register_apns_device,
    save_notification_preferences,
    save_result_subscription,
    save_subscription,
    unregister_apns_device,
)
from service import grace_marks_service
from utils.auth import require_admin_key
from utils.helpers import validateRollNo, validateconstrastRollNos
from utils.logger import logger


router = APIRouter()

MCP_SETUP_PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "mcp_setup.html",
)


def create_routes(app: FastAPI):
    """Creates routes and injects the FastAPI app instance."""

    @router.get("/", include_in_schema=False)
    async def index():
        # Docs are disabled in production, so land on the MCP setup page there.
        return RedirectResponse(url="/connect" if IS_PRODUCTION else "/docs")

    @router.get("/connect", include_in_schema=False)
    async def mcp_connect():
        """Serve the MCP connector setup guide."""
        return FileResponse(MCP_SETUP_PAGE, media_type="text/html")

    @router.get(
        "/api/getAllResult",
        operation_id="get_all_result",
        summary="Fetch every exam attempt for a student",
        description=(
            "Returns the COMPLETE attempt history for a single student, grouped per "
            "semester. Each semester contains a list of exams (regular, supplementary, "
            "RCRV-revaluation, Grace) and each exam holds the subject grades exactly "
            "as recorded for that attempt — nothing is collapsed or deduplicated. "
            "Use this when the caller wants to see EVERY attempt, including failed "
            "regulars later cleared via supplementary. Do NOT use this for SGPA/CGPA "
            "or the effective mark sheet — call getAcademicResult for the consolidated "
            "rollup instead. Cached in Redis under `<rollNo>ALL`; on cache+DB miss the "
            "scrape is queued via RabbitMQ and a pending response is returned."
        ),
        tags=["Results"],
    )
    async def get_all_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_all_results(app, roll_no)

    @router.get(
        "/api/getAcademicResult",
        operation_id="get_academic_result",
        summary="Fetch the consolidated final mark sheet",
        description=(
            "Returns the CONSOLIDATED final mark sheet for a single student. For each "
            "subject, the highest grade across all attempts (regular, supplementary, "
            "RCRV, Grace) is kept — so if a student failed the regular exam and "
            "cleared the supplementary, the supply grade wins. From that best-attempt "
            "set the response computes per-semester SGPA, semester credits, semester "
            "backlog count, an overall CGPA, total credits, and total backlogs. This "
            "is the right tool for `What is this student's effective academic "
            "standing?`. For raw per-attempt history, call getAllResult; for only the "
            "still-failing subjects, call getBacklogs. Cached in Redis under "
            "`<rollNo>Results`; falls back to a queued scrape on miss."
        ),
        tags=["Results"],
    )
    async def get_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_results(app, roll_no)

    @router.get(
        "/api/getCMM",
        operation_id="get_cmm",
        summary="Download a watermarked CMM sample PDF",
        description=(
            "Builds a clearly watermarked, non-official CMM illustration from the "
            "student's consolidated best-attempt result. Returns a PDF attachment "
            "when result data is available. On a cache/database miss, queues the "
            "usual result scrape and returns that JSON status response instead."
        ),
        tags=["Results"],
        responses={
            200: {
                "description": "Watermarked CMM sample PDF",
                "content": {"application/pdf": {}},
            },
            202: {"description": "Result scrape queued"},
        },
    )
    async def get_cmm(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_cmm(app, roll_no)

    @router.get(
        "/api/getBacklogs",
        operation_id="get_backlogs",
        summary="List subjects the student has not yet cleared",
        description=(
            "Lists subjects the student has NOT yet cleared across any attempt — i.e. "
            "the best grade per subject is still F or Ab. The response contains only "
            "the failing semesters, only the failing subjects within those semesters, "
            "and a `totalBacklogs` count. Distinct from getAcademicResult (which "
            "includes every subject) and from grace-marks/eligibility (which uses the "
            "backlog list as input to decide grace eligibility)."
        ),
        tags=["Results"],
    )
    async def get_backlogs(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_backlogs(app, roll_no)

    @router.get(
        "/api/getCreditsChecker",
        operation_id="get_credits_checker",
        summary="Compute obtained vs required credits by academic year",
        description=(
            "Computes credits earned vs the regulation's required-credits table for "
            "the student's roll-number / regulation. Returns `totalObtainedCredits`, "
            "`totalRequiredCredits`, and a year-by-year breakdown showing each "
            "academic year's two semesters, credits obtained per semester, and the "
            "year's incremental credit target. B.Tech only — returns a failure "
            "message for other degrees / regulations."
        ),
        tags=["Results"],
    )
    async def get_credits_checker(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_required_credits(app, roll_no)

    @router.get(
        "/api/getResultContrast",
        operation_id="get_result_contrast",
        summary="Side-by-side comparison of two students",
        description=(
            "Side-by-side comparison of EXACTLY TWO students' consolidated results. "
            "Returns each student's profile (name, college code, father name, CGPA, "
            "backlogs, credits) plus a per-semester comparison row (SGPA, credits, "
            "grades, backlogs, failed flag) — semesters one student doesn't have are "
            "filled with `-` placeholders. Both roll numbers are validated and each "
            "is scraped on miss. Use only when comparing two specific students."
        ),
        tags=["Results"],
    )
    async def get_result_contrast(
        roll_nos: list[str] = Depends(validateconstrastRollNos),
    ):
        return await fetch_result_contrast(app, roll_nos[0], roll_nos[1])

    @router.get(
        "/api/grace-marks/eligibility",
        operation_id="check_grace_marks_eligibility",
        summary="Check JNTUH grace-marks eligibility",
        description=(
            "Determines whether a final-year student is eligible for the JNTUH "
            "grace-marks scheme. Requires that 4-2 results have already synced into "
            "the database; B.Tech and B.Pharm only (rejected for other degrees). On "
            "success returns the student's backlog list (the same shape as "
            "getBacklogs) — the frontend uses that list to render which subjects can "
            "be raised by grace marks. Returns 404 if the roll number has no record, "
            "and 406 if the student has already cleared every subject (grace marks "
            "do not apply). Pair with grace-marks/proof for the supporting payload."
        ),
        tags=["Results"],
    )
    async def check_grace_marks_eligibility(
        roll_no: str = Depends(validateRollNo),
    ):
        return await grace_marks_service.check_eligibility(app, roll_no)

    @router.post(
        "/api/grace-marks/proof",
        summary="Upload grace-marks proof document",
        description=(
            "Uploads the supporting JNTUH sheet (PDF or image, ≤5MB) for a "
            "grace-marks eligible student. Re-verifies eligibility with the same "
            "logic as grace-marks/eligibility, then verifies that the document is "
            "a Consolidated Marks Memo (CMM). Only a confirmed CMM is stored in "
            "S3 and recorded in the database. Per-IP rate limit: 5/minute."
        ),
        tags=["Results"],
    )
    @limiter.limit("5/minute")
    async def upload_grace_marks_proof(
        request: Request,
        roll_no: str = Depends(validateRollNo),
        file: UploadFile = File(...),
    ):
        return await grace_marks_service.upload_proof(app, roll_no, file)

    @router.get(
        "/api/grace-marks/proofs/pending",
        summary="List pending grace-marks proofs (admin)",
        description=(
            "Returns up to 10 `grace_marks_proof` rows whose status is still "
            "`pending`, oldest first, with a 1-hour presigned GET URL per file. "
            "Requires `X-Admin-Key` matching `GRACE_MARKS_ADMIN_KEY` in the env "
            "— missing or wrong key both return 401. Per-IP rate limit: 10/minute."
        ),
        tags=["Results"],
        include_in_schema=False,
    )
    @limiter.limit("10/minute")
    async def list_pending_grace_marks_proofs(
        request: Request,
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ):
        return await grace_marks_service.list_pending_proofs(app, x_admin_key)

    @router.get(
        "/api/grace-marks/proofs/{proof_id}",
        summary="Get one grace-marks proof with presigned URL + backlogs (admin)",
        description=(
            "Returns a single `grace_marks_proof` row with a 1-hour presigned "
            "GET URL for the uploaded file and the student's current backlog "
            "payload (same shape as `/api/getBacklogs`). Requires `x-api-key` "
            "matching `GRACE_MARKS_ADMIN_KEY`. Returns 404 if the id is unknown. "
            "Per-IP rate limit: 10/minute."
        ),
        tags=["Results"],
        include_in_schema=False,
    )
    @limiter.limit("10/minute")
    async def get_grace_marks_proof_route(
        request: Request,
        proof_id: str,
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ):
        return await grace_marks_service.get_proof_with_backlogs(
            app, proof_id, x_admin_key
        )

    @router.patch(
        "/api/grace-marks/proofs/{proof_id}/status",
        summary="Update grace-marks proof review status (admin)",
        description=(
            "Sets the `status` of a `grace_marks_proof` row to `approved` or "
            "`rejected`. Requires `x-api-key` matching `GRACE_MARKS_ADMIN_KEY`. "
            "Returns 404 if the proof id is unknown. Body: "
            '`{"status": "approved" | "rejected"}`. Per-IP rate limit: '
            "10/minute."
        ),
        tags=["Results"],
        include_in_schema=False,
        dependencies=[Depends(require_admin_key)],
    )
    @limiter.limit("10/minute")
    async def update_grace_marks_proof_status_route(
        request: Request,
        proof_id: str,
        payload: ProofStatusUpdate,
    ):
        return await grace_marks_service.update_proof_status(app, proof_id, payload)

    @router.post(
        "/api/grace-marks/marks",
        summary="Insert grace-marks rows for a student (admin)",
        description=(
            "Inserts one `mark` row per supplied subject with `graceMarks=true`, "
            "`rcrv=false`. For each subject the `semesterCode` and `examCode` are "
            "copied from the student's most-recent existing mark for that subject "
            "(the payload's `semesterCode` is accepted but ignored). Requires "
            "`x-api-key` matching `GRACE_MARKS_ADMIN_KEY`. Returns 404 if the "
            "roll number is unknown or any subjectCode has no prior mark to "
            "anchor to — in that case nothing is inserted. Re-running the same "
            "payload upserts (updates) the existing grace row in place. After a "
            "successful write the student's Redis caches are invalidated. "
            "Per-IP rate limit: 10/minute."
        ),
        tags=["Results"],
        include_in_schema=False,
        dependencies=[Depends(require_admin_key)],
    )
    @limiter.limit("10/minute")
    async def apply_grace_marks_route(
        request: Request,
        payload: GraceMarksPayload,
    ):
        return await grace_marks_service.apply_grace_marks(app, payload)

    @router.get(
        "/api/getClassResults",
        operation_id="get_class_results",
        summary="Fetch results for an entire class section",
        description=(
            "Returns results for an ENTIRE class section, derived from the first 8 "
            "characters of the supplied roll number. Internally also looks up the "
            "paired day/evening cohort by swapping the 5th char (rule: `5↔A` per "
            "JNTUH roll convention). The `type` query parameter selects the view "
            "rendered for each student: `academicresult` (default) → consolidated "
            "mark sheet (same shape as getAcademicResult), `allresult` → full attempt "
            "history (same as getAllResult), `backlog` → backlogs-only (same as "
            "getBacklogs). Returns HTTP 423 LOCKED if the scrape queue is over "
            "capacity. Cached in Redis under `<class>Results+<type>` for 10 minutes."
        ),
        tags=["Results"],
    )
    async def get_class_result(
        roll_number: str = Depends(validateRollNo), type="academicresult"
    ):
        return await fetch_class_results(app, roll_number, type)

    @router.get(
        "/api/hardRefresh",
        summary="Hard Refresh",
        description="Refresh the result of student",
        tags=["Results"],
    )
    async def hard_refresh(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_results_using_hard_refresh(app, roll_no)

    @router.get(
        "/api/notifications",
        operation_id="get_notifications",
        summary="Fetch result notifications (paginated, filterable)",
        description=(
            "Paginated JNTUH result notifications, filterable by `regulation`, "
            "`degree`, `year`, `title`, and `category` (only `results` or `all` are "
            "honored — any other category returns an empty list). Cached in Redis "
            "for 5 minutes per filter combination. Use this for a filterable "
            "browsing feed; for the homepage `latest` strip use "
            "getlatestnotifications instead."
        ),
        tags=["Notifications"],
    )
    async def get_notifications(
        page: int,
        category: str = "all",
        regulation: str = "",
        degree: str = "",
        year: str = "",
        title: str = "",
    ):
        return await notification(page, category, regulation, degree, year, title)

    @router.get(
        "/api/refreshnotifications",
        summary="Refresh notifications",
        description="Retrieves all the notifications.",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def refresh_notifications():
        return await refreshNotification(app)

    @router.get(
        "/api/getlatestnotifications",
        operation_id="get_latest_notifications",
        summary="Get the most-recent result notifications (homepage feed)",
        description=(
            "Returns the most-recent result notifications across all categories — "
            "the homepage `latest` feed. No filters and no pagination; cached in "
            "Redis for 5 minutes. For a filterable / paginated browse use "
            "getNotifications."
        ),
        tags=["Notifications"],
    )
    async def get_latest_notifications():
        return await getLatestNotifications()

    @router.get(
        "/api/calendars",
        operation_id="get_calendars",
        summary="Fetch academic calendars",
        description=(
            "Returns JNTUH academic calendars as a nested tree keyed by "
            "academic year → degree → study year → { calendar title: PDF link }. "
            "Sourced from the `academic_calendar` table and cached in Redis."
        ),
        tags=["Content"],
    )
    async def get_calendars_route():
        return await getCalendars()

    @router.get(
        "/api/syllabus",
        operation_id="get_syllabus",
        summary="Fetch syllabus",
        description=(
            "Returns the JNTUH syllabus as a nested tree keyed by degree → "
            "regulation → category → [ { title, link } ]. Degrees without a "
            "regulation collapse to degree → category → [...]. Sourced from the "
            "`syllabus` table and cached in Redis."
        ),
        tags=["Content"],
    )
    async def get_syllabus_route():
        return await getSyllabus()

    @router.post(
        "/api/chatbot",
        response_model=ChatResponse,
        summary="Chat with the JNTUH results assistant",
        description=(
            "Runs a bounded agent that may use only the read-only operations "
            "exposed by this application's MCP allowlist. Prior user/assistant "
            "messages are optional. Per-IP rate limit: 10/minute."
        ),
        tags=["Chatbot"],
    )
    @limiter.limit("10/minute")
    async def chatbot(request: Request, payload: ChatRequest):
        try:
            return await request.app.state.chatbot_service.chat(payload)
        except ChatbotNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ChatbotUpstreamTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except (ChatbotResponseError, ChatbotUpstreamError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post(
        "/save-subscription",
        summary="Save Subscription",
        description="Save the subscription for notification for particular device.",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def save_subscription_end_point(data: PushSub):
        return await save_subscription(data)

    @router.post(
        "/api/result-subscriptions",
        status_code=status.HTTP_201_CREATED,
        summary="Subscribe a device to one student's result updates",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def save_result_subscription_endpoint(
        data: ResultDeviceSubscriptionPayload,
    ):
        return await save_result_subscription(data)

    @router.delete(
        "/api/result-subscriptions",
        summary="Delete every result subscription for a device",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def delete_result_subscriptions_endpoint(
        device_id: UUID = Query(alias="deviceId"),
    ):
        return await delete_result_subscriptions(str(device_id))

    @router.put(
        "/api/push-devices",
        status_code=status.HTTP_201_CREATED,
        summary="Register an iOS device for result-release notifications",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def register_push_device_endpoint(data: APNSDeviceRegistrationPayload):
        return await register_apns_device(data)

    @router.delete(
        "/api/push-devices",
        summary="Unregister an iOS device from result-release notifications",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def unregister_push_device_endpoint(
        device_id: UUID = Query(alias="deviceId"),
    ):
        return await unregister_apns_device(str(device_id))

    @router.put(
        "/api/notification-preferences",
        status_code=status.HTTP_201_CREATED,
        summary="Save a device's degree/regulation result-notification filter",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def save_notification_preferences_endpoint(
        data: NotificationPreferencePayload,
    ):
        return await save_notification_preferences(data)

    @router.get(
        "/api/notification-preferences",
        summary="Get a device's saved result-notification filter",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def get_notification_preferences_endpoint(
        device_id: UUID = Query(alias="deviceId"),
    ):
        return await get_notification_preferences(str(device_id))

    @router.delete(
        "/api/notification-preferences",
        summary="Reset a device's result-notification filter to the default (all)",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def delete_notification_preferences_endpoint(
        device_id: UUID = Query(alias="deviceId"),
    ):
        return await delete_notification_preferences(str(device_id))

    @router.get(
        "/api/jobs",
        operation_id="get_jobs",
        summary="Get India fresher and internship engineering jobs",
        description=(
            "Returns active India-eligible engineering internships and fresher jobs. "
            "Results can be filtered by employment type, company classification, "
            "company, source, remote status, or keyword."
        ),
        tags=["Jobs"],
    )
    async def get_jobs_endpoint(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
        type: str = Query(default="", max_length=30),
        keyword: str = Query(default="", max_length=100),
        source: str = Query(default="", max_length=100),
        company: str = Query(default="", max_length=100),
        company_type: str = Query(default="", alias="companyType", max_length=20),
        remote: bool | None = Query(default=None),
    ):
        normalized_type = type.upper()
        normalized_company_type = company_type.upper()
        if normalized_type not in {"", "INTERN", "FULL_TIME", "PART_TIME"}:
            raise HTTPException(status_code=422, detail="Invalid job type")
        if normalized_company_type not in {"", "PRODUCT", "SERVICE", "OTHER"}:
            raise HTTPException(status_code=422, detail="Invalid company type")
        return await fetch_jobs(
            page=page,
            page_size=page_size,
            type=normalized_type,
            keyword=keyword,
            source=source,
            company=company,
            company_type=normalized_company_type,
            remote=remote,
        )

    async def _readiness_status() -> dict:
        """Probe each dependency the API needs. Never raises — a probe
        failure is reported as that dependency's status, not a 500."""
        checks: dict[str, str] = {}

        try:
            await prismaConnection.prisma.query_raw("SELECT 1")
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001 - liveness probe, not a bug
            logger.error("Readiness check: database probe failed", exc_info=exc)
            checks["database"] = "error"

        try:
            if redisConnection.client and redisConnection.client.ping():
                checks["redis"] = "ok"
            else:
                checks["redis"] = "error"
        except Exception as exc:  # noqa: BLE001
            logger.error("Readiness check: redis probe failed", exc_info=exc)
            checks["redis"] = "error"

        rabbitmq_connection = getattr(app.state, "rabbitmq_connection", None)
        checks["rabbitmq"] = (
            "ok"
            if rabbitmq_connection is not None and not rabbitmq_connection.is_closed
            else "error"
        )

        return checks

    @router.get("/api/health/live", include_in_schema=False)
    async def get_health_live():
        """Liveness only: the process is up and answering HTTP. Exempt from
        the X-Api-Key guard (see config/apiHeaderGuard.py) so the container
        HEALTHCHECK doesn't need a secret."""
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "success"},
        )

    @router.get("/api/health/ready", include_in_schema=False)
    async def get_health_ready():
        """Readiness with a per-dependency breakdown. Kept behind X-Api-Key
        (not exempt) since it discloses internal infra status."""
        checks = await _readiness_status()
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "success" if healthy else "error",
                "checks": checks,
            },
        )

    @router.get("/api/health")
    async def get_health():
        """Public alias kept for existing external uptime monitors. Reports
        only an overall status (no dependency breakdown, unlike /api/health/ready)
        since this path stays exempt from the X-Api-Key guard."""
        checks = await _readiness_status()
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "success" if healthy else "error",
                "message": "The health is good." if healthy else "One or more dependencies are unavailable.",
            },
        )

    return router
    register_apns_device,
