from fastapi import APIRouter, FastAPI, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse

from database.models import PushSub
from service.getAllResultService import fetch_all_results
from service.getBacklogsService import fetch_backlogs
from service.getClassResults import fetch_class_results
from service.getRequiredCreditsService import fetch_required_credits
from service.getResultContrastService import fetch_result_contrast
from service.getResultsService import fetch_results
from service.hardrefresh import fetch_results_using_hard_refresh
from service.notificationService import (
    getLatestNotifications,
    notification,
    refreshNotification,
)
from service.subscriptionService import save_subscription
from service import grace_marks_service
from utils.helpers import validateRollNo, validateconstrastRollNos


router = APIRouter()


def create_routes(app: FastAPI):
    """Creates routes and injects the FastAPI app instance."""

    @router.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse(url="/docs")

    @router.get(
        "/api/getAllResult",
        summary="Fetch all student results",
        description="Retrieves the full academic record for all students.",
        tags=["Results"],
    )
    async def get_all_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_all_results(app, roll_no)

    @router.get(
        "/api/getAcademicResult",
        summary="Fetch academic results",
        description="Retrieves a specific student's academic results based on query parameters.",
        tags=["Results"],
    )
    async def get_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_results(app, roll_no)

    @router.get(
        "/api/getBacklogs",
        summary="Fetch student backlogs",
        description="Retrieves a list of backlogs (pending subjects) for a student.",
        tags=["Results"],
    )
    async def get_backlogs(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_backlogs(app, roll_no)

    @router.get(
        "/api/getCreditsChecker",
        summary="Get Required Credits",
        description="Retrives required credits for a student",
        tags=["Results"],
    )
    async def get_credits_checker(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_required_credits(app, roll_no)

    @router.get(
        "/api/getResultContrast",
        summary="Get Result Contrast ",
        description="Retrives difference between two students marks",
        tags=["Results"],
    )
    async def get_result_contrast(
        roll_nos: list[str] = Depends(validateconstrastRollNos),
    ):
        return await fetch_result_contrast(app, roll_nos[0], roll_nos[1])

    @router.get(
        "/api/grace-marks/eligibility",
        summary="Check grace marks eligibility",
        description="API to check whether a student is eligible for grace marks",
        tags=["Results"],
    )
    async def check_grace_marks_eligibility(
        roll_no: str = Depends(validateRollNo),
    ):
        return await grace_marks_service.check_eligibility(app, roll_no)

    @router.get(
        "/api/grace-marks/proof",
        summary="Get grace marks proof",
        description="API to fetch or submit proof related to grace marks",
        tags=["Results"],
    )
    async def get_grace_marks_proof(
        roll_no: str = Depends(validateRollNo),
    ):
        return await grace_marks_service.get_proof(app, roll_no)

    @router.get(
        "/api/getClassResults",
        summary="Get Class Results ",
        description="Retrives the results of the class",
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
        summary="Fetch result notifications",
        description="Retrieves  the notifications for the specified filters.",
        tags=["Notifications"],
    )
    async def get_notifications(
        page: int,
        regulation: str = "",
        degree: str = "",
        year: str = "",
        title: str = "",
    ):
        return await notification(page, regulation, degree, year, title)

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
        summary="Get Latest notifications",
        description="Retrieves latest  notifications.",
        tags=["Notifications"],
    )
    async def get_latest_notifications():
        return await getLatestNotifications()

    @router.post(
        "/save-subscription",
        summary="Save Subscription",
        description="Save the subscription for notification for particular device.",
        tags=["Notifications"],
        include_in_schema=False,
    )
    async def save_subscription_end_point(data: PushSub):
        return await save_subscription(data)

    @router.get("/health")
    async def get_health():
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": "The health is good.",
            },
        )

    return router
