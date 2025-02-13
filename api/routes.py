from fastapi import APIRouter, FastAPI, Depends

from service.getAllResultService import fetch_all_results
from service.getResultsService import fetch_results
from utils.helpers import validateRollNo

router = APIRouter()


def create_routes(app: FastAPI):
    """Creates routes and injects the FastAPI app instance."""

    @router.get("/api/getAllResult")
    async def get_all_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_all_results(app, roll_no)

    @router.get("/api/getAcademicResult")
    async def get_result(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_results(app, roll_no)

    @router.get("/api/getBacklogs")
    async def get_backlogs(
        roll_no: str = Depends(validateRollNo),
    ):
        return await fetch_results(app, roll_no)

    return router
