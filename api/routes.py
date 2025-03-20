from fastapi import APIRouter, FastAPI, Depends
from fastapi.responses import RedirectResponse

from service.getAllResultService import fetch_all_results
from service.getBacklogsService import fetch_backlogs
from service.getRequiredCreditsService import fetch_required_credits
from service.getResultContrastService import fetch_result_contrast
from service.getResultsService import fetch_results
from service.notificationService import notification
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
        "/api/notifications",
        summary="Fetch result notifications",
        description="Retrieves all the notifications.",
        tags=["Notifications"],
    )
    async def get_notifications():
        return await notification(app)

    return router
