import os

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse

from config.rateLimiter import limiter
from config.settings import IS_PRODUCTION
from chatbot.errors import (
    ChatbotNotConfiguredError,
    ChatbotResponseError,
    ChatbotUpstreamError,
    ChatbotUpstreamTimeoutError,
)
from chatbot.schemas import ChatRequest, ChatResponse
from database.models import GraceMarksPayload, ProofStatusUpdate, PushSub
from service.getAllResultService import fetch_all_results
from service.getBacklogsService import fetch_backlogs
from service.getClassResults import fetch_class_results
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
from service.subscriptionService import save_subscription
from service import grace_marks_service
from utils.auth import require_admin_key
from utils.helpers import validateRollNo, validateconstrastRollNos


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
            "logic as grace-marks/eligibility before storing the file in S3 and "
            "recording its location. Per-IP rate limit: 5/minute."
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
        "/job",
        summary="Job Posting",
        description="Save the job detail",
        tags=["Jobs"],
        include_in_schema=True,
    )
    @router.get("/api/health")
    async def get_health():
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": "The health is good.",
            },
        )

    return router
