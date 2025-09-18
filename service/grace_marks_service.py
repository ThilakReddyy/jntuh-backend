from database.models import studentBacklogs, studentDetailsModel
from database.operations import check_4_2_semester, get_details


async def check_eligibility(app, roll_no: str):
    if roll_no[5] != "A" and roll_no[5] != "R":
        return {
            "status": "failure",
            "message": "This Feature is currently only available for Btech and Bpharm Students",
        }
    if not await check_4_2_semester(roll_no):
        return {
            "status": "failure",
            "message": "Your 4-2 semester marks haven't yet synced",
        }

    response = await get_details(roll_no)
    if response:
        _, marks = response
        backlogs = studentBacklogs(marks, False)
        return backlogs
    return {
        "status": "failure",
        "message": "Unable to find your roll number",
    }


async def get_proof(app, roll_no: str):
    # Your logic here (DB query, conditions, etc.)
    return {"roll_no": roll_no, "eligible": True}
