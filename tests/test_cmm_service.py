import asyncio
import copy
import json
import os
import sys
from pathlib import Path

import pytest

from fastapi import status
from fastapi.responses import JSONResponse


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for name, value in {
    "RABBITMQ_URL": "amqp://guest:guest@localhost/",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/jntuh",
    "QUEUE_NAME": "test",
    "REDIS_URL": "redis://localhost:6379/0",
    "VAPID_PUBLIC_KEY": "test",
    "VAPID_PRIVATE_KEY": "test",
    "TELEGRAM_TOKEN": "test",
    "TELEGRAM_CHAT_ID": "test",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_REGION": "us-east-1",
    "S3_BUCKET_NAME": "test",
    "GRACE_MARKS_ADMIN_KEY": "test",
}.items():
    os.environ.setdefault(name, value)

from service import cmm_pdf  # noqa: E402
from service import getCMMService  # noqa: E402
from service.cmm_pdf import generate_cmm_pdf  # noqa: E402


PAYLOAD = {
    "details": {
        "name": "Test Student",
        "rollNumber": "22XX1A0501",
        "collegeCode": "XX",
        "fatherName": "Test Parent",
        "branch": "Computer Science and Engineering",
    },
    "results": {
        "semesters": [
            {
                "semester": "1-1",
                "subjects": [
                    {
                        "subjectName": "Mathematics",
                        "grades": "A",
                        "credits": 4,
                    }
                ],
            }
        ],
        "CGPA": "8.00",
        "credits": 4,
    },
}


def test_generate_cmm_pdf_returns_a_pdf_document():
    pdf = generate_cmm_pdf(PAYLOAD)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000
    assert b"https://jntuhconnect.dhethi.com" in pdf


def test_fetch_cmm_returns_downloadable_pdf(monkeypatch):
    async def result_found(_app, _roll_number):
        return PAYLOAD

    monkeypatch.setattr(getCMMService, "fetch_results", result_found)
    response = asyncio.run(getCMMService.fetch_cmm(None, "22XX1A0501"))

    assert response.status_code == status.HTTP_200_OK
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")
    assert response.headers["content-disposition"] == (
        'attachment; filename="CMM-22XX1A0501.pdf"'
    )
    assert response.headers["cache-control"] == "private, no-store"


def test_fetch_cmm_preserves_pending_lookup_response(monkeypatch):
    pending = JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "success", "message": "Your roll number has been queued."},
    )

    async def result_pending(_app, _roll_number):
        return pending

    monkeypatch.setattr(getCMMService, "fetch_results", result_pending)
    response = asyncio.run(getCMMService.fetch_cmm(None, "22XX1A0501"))

    assert response is pending
    assert json.loads(response.body)["message"] == "Your roll number has been queued."


class RecordingCanvas:
    """Minimal canvas that records the filled rectangles a barcode draws."""

    def __init__(self):
        self.rects = []
        self._origin = (0.0, 0.0)

    def saveState(self):
        pass

    def restoreState(self):
        self._origin = (0.0, 0.0)

    def translate(self, x, y):
        self._origin = (x, y)

    def setFillColor(self, _color):
        pass

    def rect(self, x, y, w, h, stroke=0, fill=1):
        self.rects.append((self._origin[0] + x, self._origin[1] + y, w, h))


def draw_barcode(value, x=80.0, y=700.0, width=140.0, height=20.0):
    """Return only the bar rectangles, dropping the background wash."""
    canvas = RecordingCanvas()
    cmm_pdf.barcode(canvas, x, y, width, height, 3, value)
    return [r for r in canvas.rects if r[3] == height]


def test_barcode_encodes_the_roll_number_and_fills_the_requested_width():
    width, x = 140.0, 80.0
    bars = draw_barcode("22XX1A0501", x=x, width=width)

    assert bars, "expected Code 128 bars to be drawn"

    quiet = width / (
        cmm_pdf.code128.Code128(
            "22XX1A0501", barWidth=1, humanReadable=False, quiet=True,
            lquiet=cmm_pdf.QUIET_MODULES, rquiet=cmm_pdf.QUIET_MODULES,
        ).width
    ) * cmm_pdf.QUIET_MODULES

    # Symbol sits inside the slot, with a full quiet zone on each side.
    assert bars[0][0] == pytest.approx(x + quiet, abs=0.01)
    last = bars[-1]
    assert last[0] + last[2] == pytest.approx(x + width - quiet, abs=0.01)


def test_barcode_pattern_depends_on_the_roll_number():
    assert draw_barcode("22XX1A0501") != draw_barcode("22XX1A0502")
    assert draw_barcode("22XX1A0501") == draw_barcode("22XX1A0501")


def test_barcode_falls_back_to_decorative_bars_without_a_value():
    for empty in (None, "", "----"):
        assert draw_barcode(empty), f"expected fallback bars for {empty!r}"

    assert draw_barcode("") == draw_barcode(None)
    assert draw_barcode("") != draw_barcode("22XX1A0501")


def test_generated_pdf_varies_with_the_roll_number():
    other = copy.deepcopy(PAYLOAD)
    other["details"]["rollNumber"] = "22XX1A0502"

    assert generate_cmm_pdf(PAYLOAD) != generate_cmm_pdf(other)
