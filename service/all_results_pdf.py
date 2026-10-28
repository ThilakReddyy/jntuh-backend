"""Render the complete attempt history as one PDF, with a memo per exam code."""

from functools import partial
from io import BytesIO
from math import cos, isfinite, pi, sin
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCode
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, LongTable, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, TableStyle,
)

from service.cmm_pdf import PAGE_H, PAGE_W, fit
from utils.helpers import gradestogpa, gradestogpabppharamcyr22, isbpharmacyr22


INK = HexColor("#302D3A")
RULE = HexColor("#83798A")
PAPER = HexColor("#FDFCFD")
BAND = HexColor("#F2EFF4")
WIDTH = PAGE_W - 80
CELL = ParagraphStyle("memo-cell", fontName="Helvetica", fontSize=8, leading=11, textColor=INK)
CENTER = ParagraphStyle("memo-center", parent=CELL, alignment=1)
HEADING = ParagraphStyle("memo-heading", parent=CENTER, fontName="Helvetica-Bold", fontSize=6.5, leading=8)


def _paragraph(value, style=CELL):
    # Subject titles and student names are data, never ReportLab markup.
    return Paragraph(escape(str(value if value is not None else "-")), style)


def _grade_scale(details):
    roll = str(details.get("rollNumber", ""))
    pharmacy = len(roll) == 10 and roll[:2].isdigit() and isbpharmacyr22(roll)
    scale = gradestogpabppharamcyr22 if pharmacy else gradestogpa
    return {grade.upper(): points for grade, points in scale.items() if points > 0}


def _radial_half(c, edge, *, upper):
    """Place a half-rosette against an actual table edge."""
    form = "all-results-radial-pattern"
    if not c.hasForm(form):
        c.beginForm(form, -650, -650, 650, 650)
        c.setStrokeColor(HexColor("#C8C1CE"))
        c.setLineWidth(0.28)
        for radius in range(4, 650, 4):
            path = c.beginPath()
            for step in range(361):
                angle = step * pi / 180
                wave = min(radius * 0.16, 8) * sin(16 * angle + radius / 35)
                r = radius + wave
                x, y = r * cos(angle), r * sin(angle)
                if step == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.close()
            c.drawPath(path)
        c.endForm()
    c.saveState()
    clip = c.beginPath()
    bottom, top = (edge, PAGE_H - 22) if upper else (22, edge)
    clip.rect(22, bottom, PAGE_W - 44, top - bottom)
    c.clipPath(clip, stroke=0, fill=0)
    c.translate(PAGE_W / 2, edge)
    c.doForm(form)
    c.restoreState()


def _memo_background(c, table_top, table_bottom):
    """Border and radial halves positioned above and below the rendered table."""
    # Draw after table layout so short tables and continuation pages each get
    # their own correct lower anchor. The clip preserves the existing table.
    c.saveState()
    clip = c.beginPath()
    clip.rect(0, 0, PAGE_W, PAGE_H)
    # Preserve the grid strokes, which extend just outside the table bounds.
    clip.rect(39.7, table_bottom - 0.3, WIDTH + 0.6, table_top - table_bottom + 0.6)
    c.clipPath(clip, stroke=0, fill=0, fillMode=0)
    _memo_paper(c)
    _radial_half(c, table_top, upper=True)
    _radial_half(c, table_bottom, upper=False)
    # Wavy side curves meet the radial halves at the same position and slope.
    # Fade the extra ripple at both ends to avoid kinks at the table corners.
    side_clip = c.beginPath()
    side_clip.rect(22, table_bottom, PAGE_W - 44, table_top - table_bottom)
    c.clipPath(side_clip, stroke=0, fill=0)
    c.setStrokeColor(HexColor("#C8C1CE"))
    c.setLineWidth(0.28)
    height = table_top - table_bottom
    cycles = max(1, round(height / 72))
    steps = max(32, int(height / 2))
    for radius in range(4, 650, 4):
        amplitude = min(radius * 0.16, 8)
        r = radius + amplitude * sin(radius / 35)
        slope = 16 * amplitude * cos(radius / 35) / r
        for side in (-1, 1):
            base_x = PAGE_W / 2 + side * r
            # Include nearby curves that bend into the visible side strips.
            if not (10 <= base_x <= 52 or PAGE_W - 52 <= base_x <= PAGE_W - 10):
                continue
            path = c.beginPath()
            for step in range(steps + 1):
                t = step / steps
                angle = 2 * pi * cycles * t
                bend = slope * height / (2 * pi * cycles) * sin(angle)
                ripple = side * 5 * sin(pi * t) ** 2 * sin(angle + radius / 45)
                x, y = base_x + bend + ripple, table_bottom + height * t
                if step == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            c.drawPath(path)
    c.restoreState()


def _memo_paper(c):
    """Reuse the plain paper and interlaced border on every page."""
    form = "all-results-memo-paper"
    if c.hasForm(form):
        c.doForm(form)
        return
    c.beginForm(form, 0, 0, PAGE_W, PAGE_H)
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#807386"))
    c.setLineWidth(0.35)
    for phase in range(6):
        offset = phase * pi / 3
        for horizontal in (True, False):
            length = PAGE_W if horizontal else PAGE_H
            for edge in (14, (PAGE_H if horizontal else PAGE_W) - 14):
                path = c.beginPath()
                for step in range(10, int(length - 9)):
                    wave = edge + 3.4 * sin(step * pi / 5 + offset)
                    x, y = (step, wave) if horizontal else (wave, step)
                    if step == 10:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                c.drawPath(path)
    for inset in (9, 20):
        c.rect(inset, inset, PAGE_W - inset * 2, PAGE_H - inset * 2, fill=0, stroke=1)

    c.endForm()
    c.doForm(form)


def _page(c, doc, *, details, semester, exam):
    c.saveState()
    _memo_background(c, *doc.table_bounds)
    fit(c, "JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY HYDERABAD", 44, 791, WIDTH - 8, 11, True, "center")
    fit(c, "HYDERABAD, TELANGANA - 500 085", 40, 774, WIDTH, 8, align="center")
    c.setFillColor(INK)
    c.roundRect(176, 740, 260, 22, 9, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(PAGE_W / 2, 748, "MEMORANDUM OF MARKS")

    roll = details.get("rollNumber", "-")
    fit(c, "NAME", 42, 718, 110, 7, True)
    fit(c, details.get("name", "-"), 155, 718, 407, 9, True)
    fit(c, "BRANCH", 42, 698, 110, 7, True)
    fit(c, details.get("branch", "-"), 155, 698, 407, 8)
    fit(c, f"SEMESTER: {semester}", 42, 677, 200, 8, True)
    fit(c, f"HALL TICKET: {roll}", 335, 677, 227, 9, True)
    fit(c, f"EXAM CODE: {exam.get('examCode', '-')}", 42, 656, 285, 8, True)
    fit(c, f"COLLEGE CODE: {details.get('collegeCode', '-')}", 335, 656, 227, 8)

    result_url = "https://jntuhconnect.dhethi.com/academicallresult/result?" + urlencode({"htno": roll})
    qr_x, qr_y, qr_size = 42, 80, 68
    # A white backing preserves the four-module quiet zone over the pattern.
    c.setFillColor(white)
    c.rect(qr_x, qr_y, qr_size, qr_size, fill=1, stroke=0)
    c.setFillColor(HexColor("#000000"))
    QrCode(result_url, width=qr_size, height=qr_size, qrBorder=4, qrLevel="M").drawOn(c, qr_x, qr_y)
    c.linkURL(result_url, (qr_x, qr_y, qr_x + qr_size, qr_y + qr_size), relative=0)
    fit(c, "jntuhconnect.dhethi.com", 190, 49, 232, 8, True, "center")
    c.linkURL("https://jntuhconnect.dhethi.com", (190, 45, 422, 59), relative=0)
    fit(c, "SAMPLE DOCUMENT - NOT VALID FOR VERIFICATION OR OFFICIAL USE", 40, 32, WIDTH, 6, True, "center")
    c.restoreState()


def _has_recorded_mark(value):
    # The result model stores unavailable marks as zero. As on the results
    # page, an entirely zero/empty column is treated as unavailable. Once a
    # column is present, individual zero scores are still printed unchanged.
    try:
        number = float(value)
        return isfinite(number) and number != 0
    except (TypeError, ValueError):
        return str(value).strip().upper() in {"AB", "ABS"}


def _exam_flowables(exam, scale):
    subjects = exam.get("subjects", [])
    mark_columns = [
        (key, title, width) for key, title, width in [
            ("internalMarks", "INT.", 36),
            ("externalMarks", "EXT.", 36),
            ("totalMarks", "TOTAL", 37),
        ] if any(_has_recorded_mark(subject.get(key)) for subject in subjects)
    ]
    headings = ["S.NO", "SUBJECT CODE", "SUBJECT TITLE"] + [title for _, title, _ in mark_columns] + ["GRADE", "GRADE POINT", "CREDITS"]
    mark_widths = [width for _, _, width in mark_columns]
    widths = [25, 54, 337 - sum(mark_widths)] + mark_widths + [35, 39, 42]
    rows = [[_paragraph(label, HEADING) for label in headings]]
    passed = 0
    credits = 0.0
    for index, subject in enumerate(subjects, 1):
        grade = str(subject.get("grades", "-")).strip().upper()
        points = scale.get(grade, 0 if grade in {"F", "AB", "ABS"} else "-")
        passed += int(grade in scale or grade == "P")
        credits += float(subject.get("credits") or 0)
        values = [
            index, subject.get("subjectCode", "-"), subject.get("subjectName", "-"),
            *[subject.get(key, "-") for key, _, _ in mark_columns],
            subject.get("grades", "-"), points,
            f"{float(subject.get('credits') or 0):g}",
        ]
        rows.append([_paragraph(value, CELL if column == 2 else CENTER) for column, value in enumerate(values)])
    if not subjects:
        rows.append([_paragraph("-", CENTER), _paragraph("-", CENTER), _paragraph("No subjects recorded for this exam.")] + [""] * (len(headings) - 3))
    rows.append([_paragraph(
        f"Registered Subjects: {len(subjects)}    |    Passed: {passed}    |    Recorded Credits: {credits:g}", CENTER,
    )] + [""] * (len(headings) - 1))

    table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("BACKGROUND", (0, 1), (-1, -1), white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("SPAN", (0, -1), (-1, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), BAND),
        # Keep the totals with the last subject rather than on an empty page.
        ("NOSPLIT", (0, -2), (-1, -1)),
    ]))
    return [table]


class _MemoDocument(BaseDocTemplate):
    def beforePage(self):
        self.table_bounds = None

    def afterFlowable(self, flowable):
        if isinstance(flowable, LongTable):
            bottom = self.frame._y + flowable.getSpaceAfter()
            top = bottom + flowable._height
            if self.table_bounds is not None:
                top = max(top, self.table_bounds[0])
                bottom = min(bottom, self.table_bounds[1])
            self.table_bounds = (top, bottom)


def generate_all_results_pdf(payload: Mapping[str, Any], output_path: str | Path | None = None) -> bytes:
    """Preserve every attempt and subject, starting each exam on a new page."""
    details, semesters = payload.get("details"), payload.get("results")
    if not isinstance(details, Mapping) or not isinstance(semesters, list):
        raise ValueError("payload must contain details and a results array")
    attempts = [(semester["semester"], exam) for semester in semesters for exam in semester.get("exams", [])]
    if not attempts:
        raise ValueError("No exam results available")
    scale = _grade_scale(details)
    buffer = BytesIO()
    doc = _MemoDocument(buffer, pagesize=(PAGE_W, PAGE_H), title=f"All Academic Results - {details.get('rollNumber', '')}", author="JNTUH Connect")
    story = []
    for index, (semester, exam) in enumerate(attempts):
        template_id = f"exam-{index}"
        doc.addPageTemplates(PageTemplate(
            id=template_id,
            frames=[Frame(40, 157, WIDTH, 460, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
            onPageEnd=partial(_page, details=details, semester=semester, exam=exam),
        ))
        if index:
            story.extend([NextPageTemplate(template_id), PageBreak()])
        story.extend(_exam_flowables(exam, scale))
    doc.build(story)
    pdf = buffer.getvalue()
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(pdf)
    return pdf
