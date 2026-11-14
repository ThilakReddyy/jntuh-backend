"""Service for serving a student's consolidated result as a CMM sample PDF."""

import json
from collections.abc import Mapping

from fastapi import FastAPI, Response, status

from service.cmm_pdf import generate_cmm_pdf
from service.getResultsService import fetch_results


async def fetch_cmm(app: FastAPI, roll_number: str) -> Response:
    """Return a PDF when results exist, otherwise preserve the result lookup response."""
    result_response = await fetch_results(app, roll_number)

    if isinstance(result_response, Response):
        if result_response.status_code != status.HTTP_200_OK:
            return result_response
        payload = json.loads(result_response.body)
    else:
        payload = result_response

    if not isinstance(payload, Mapping):
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    pdf_bytes = generate_cmm_pdf(payload)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="CMM-{roll_number}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
