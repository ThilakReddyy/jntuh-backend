"""Download exam-wise marks memos using the existing all-results lookup."""

import json
from collections.abc import Mapping

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from service.all_results_pdf import generate_all_results_pdf
from service.getAllResultService import fetch_all_results


async def fetch_all_results_pdf(app: FastAPI, roll_number: str) -> Response:
    result = await fetch_all_results(app, roll_number)
    if isinstance(result, Response):
        if result.status_code != 200:
            return result
        payload = json.loads(result.body)
    else:
        payload = result
    if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
        return JSONResponse(status_code=500, content={"message": "Invalid result data."})
    if not any(semester.get("exams") for semester in payload["results"]):
        return JSONResponse(status_code=404, content={"message": "No exam results available to download."})
    pdf = await run_in_threadpool(generate_all_results_pdf, payload)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="All-Results-{roll_number}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
