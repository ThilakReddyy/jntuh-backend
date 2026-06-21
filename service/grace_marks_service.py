from database.models import studentBacklogs
from database.operations import check_4_2_semester, get_details


async def check_eligibility(app, roll_no: str):
    """Determine whether a final-year student is eligible for the JNTUH grace-marks scheme.

    Two preconditions must hold: (1) the 5th char of the roll number must be
    `A` (B.Tech) or `R` (B.Pharm) — other degrees are rejected outright; (2)
    the student's 4-2 (final-semester) marks must already be synced into the
    DB (`check_4_2_semester`). On success the response IS the backlog list (same
    shape as `fetch_backlogs`) — the frontend uses that list to render which
    subjects can be raised by grace marks.

    Pair with `get_proof` for the supporting payload after eligibility is
    confirmed.
    """
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
    """Return the supporting payload used by the frontend to render the grace-marks justification view.

    Currently a stub that echoes `{roll_no, eligible: True}` — call AFTER
    `check_eligibility` confirms the student qualifies. Real proof generation
    (DB lookup of subjects raised, marks delta, signed payload) is intended
    to be wired here later.
    """
    return {"roll_no": roll_no, "eligible": True}
