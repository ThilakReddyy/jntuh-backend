"""Render the complete attempt history as one PDF, with a memo per exam code."""

from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, LongTable, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, TableStyle,
)

from service.cmm_pdf import PAGE_H, PAGE_W, barcode, border, fit
from utils.helpers import gradestogpa, gradestogpabppharamcyr22, isbpharmacyr22


INK = HexColor("#302D3A")
RULE = HexColor("#83798A")
PAPER = HexColor("#FAF8FC")
BAND = HexColor("#EAE5EE")
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


def _page(c, doc, *, details, semester, exam, scale):
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    border(c)
    c.setStrokeColor(HexColor("#E6E0EB"))
    c.setLineWidth(0.3)
    for y in range(35, int(PAGE_H - 30), 12):
        c.ellipse(27, y - 15, PAGE_W - 27, y + 15, fill=0, stroke=1)
    c.setFillColor(PAPER)
    c.roundRect(30, 147, PAGE_W - 60, 664, 6, fill=1, stroke=0)
    fit(c, "JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY HYDERABAD", 44, 791, WIDTH - 8, 11, True, "center")
    fit(c, "HYDERABAD, TELANGANA - 500 085", 40, 774, WIDTH, 8, align="center")
    c.setFillColor(INK)
    c.roundRect(176, 740, 260, 22, 9, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(PAGE_W / 2, 748, "MEMORANDUM OF MARKS")

    roll = details.get("rollNumber", "-")
    fit(c, "STUDENT'S NAME", 42, 718, 110, 7, True)
    fit(c, details.get("name", "-"), 155, 718, 407, 9, True)
    fit(c, "BRANCH", 42, 698, 110, 7, True)
    fit(c, details.get("branch", "-"), 155, 698, 407, 8)
    fit(c, f"SEMESTER: {semester}", 42, 677, 200, 8, True)
    fit(c, f"HALL TICKET: {roll}", 335, 677, 227, 9, True)
    fit(c, f"EXAM CODE: {exam.get('examCode', '-')}", 42, 656, 285, 8, True)
    fit(c, f"COLLEGE CODE: {details.get('collegeCode', '-')}", 335, 656, 227, 8)
    variant = "RC / RV" if exam.get("rcrv") else "Grace Marks" if exam.get("graceMarks") else "Exam result"
    fit(c, f"{variant} | Grades recorded for this attempt", 42, 636, 520, 8)

    barcode(c, 42, 113, 142, 20, value=roll)
    fit(c, str(roll), 42, 102, 142, 7, align="center")
    fit(c, f"Page {doc.page}", 465, 118, 98, 8, align="right")
    legend = "GRADE POINTS: " + "   ".join(f"{grade} = {points}" for grade, points in scale.items())
    fit(c, legend + "   F / Ab = 0", 40, 83, WIDTH, 7, align="center")
    fit(c, "Attempt history only. Semester SGPA requires the consolidated result.", 40, 67, WIDTH, 7, align="center")
    fit(c, "jntuhconnect.dhethi.com", 190, 49, 232, 8, True, "center")
    c.linkURL("https://jntuhconnect.dhethi.com", (190, 45, 422, 59), relative=0)
    fit(c, "SAMPLE DOCUMENT - NOT VALID FOR VERIFICATION OR OFFICIAL USE", 40, 32, WIDTH, 6, True, "center")
    c.restoreState()


def _exam_flowables(exam, scale):
    subjects = exam.get("subjects", [])
    headings = ["S.NO", "SUBJECT CODE", "SUBJECT TITLE", "INT.", "EXT.", "TOTAL", "GRADE", "GRADE POINT", "CREDITS"]
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
            subject.get("internalMarks", "-"), subject.get("externalMarks", "-"),
            subject.get("totalMarks", "-"), subject.get("grades", "-"), points,
            f"{float(subject.get('credits') or 0):g}",
        ]
        rows.append([_paragraph(value, CELL if column == 2 else CENTER) for column, value in enumerate(values)])
    if not subjects:
        rows.append([_paragraph("-", CENTER), _paragraph("-", CENTER), _paragraph("No subjects recorded for this exam.")] + [""] * 6)
    rows.append([_paragraph(
        f"Registered Subjects: {len(subjects)}    |    Passed: {passed}    |    Recorded Credits: {credits:g}", CENTER,
    )] + [""] * 8)

    table = LongTable(rows, colWidths=[25, 54, 228, 36, 36, 37, 35, 39, 42], repeatRows=1, hAlign="LEFT", splitInRow=1)
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
    doc = BaseDocTemplate(buffer, pagesize=(PAGE_W, PAGE_H), title=f"All Academic Results - {details.get('rollNumber', '')}", author="JNTUH Connect")
    story = []
    for index, (semester, exam) in enumerate(attempts):
        template_id = f"exam-{index}"
        doc.addPageTemplates(PageTemplate(
            id=template_id,
            frames=[Frame(40, 157, WIDTH, 460, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
            onPage=partial(_page, details=details, semester=semester, exam=exam, scale=scale),
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
