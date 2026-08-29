"""Render a watermarked CMM illustration from consolidated result data."""

from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from reportlab.graphics.barcode import code128
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = 612, 852
INK = HexColor("#17211E")
PAPER = HexColor("#EDF3E7")
PATTERN = HexColor("#C9D7C6")
LINE = HexColor("#2A342F")
GOLD = HexColor("#C79222")
# Code 128 requires a quiet zone of at least 10 modules on each side.
QUIET_MODULES = 10
BARCODE_CHARSET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
GRADE_POINTS = {
    "O": 10,
    "A+": 9,
    "A": 8,
    "B+": 7,
    "B": 6,
    "C": 5,
    "D": 5,
    "F": 0,
    "AB": 0,
    "-": "-",
}


def fit(c, text, x, y, width, size=7, bold=False, align="left"):
    text = str(text or "")
    font = "Helvetica-Bold" if bold else "Helvetica"
    actual = size
    while actual > 3.8 and stringWidth(text, font, actual) > width:
        actual -= 0.2
    if stringWidth(text, font, actual) > width:
        while text and stringWidth(text + "…", font, actual) > width:
            text = text[:-1]
        text += "…"
    c.setFont(font, actual)
    c.setFillColor(INK)
    if align == "center":
        c.drawCentredString(x + width / 2, y, text)
    elif align == "right":
        c.drawRightString(x + width, y, text)
    else:
        c.drawString(x, y, text)


def background(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setStrokeColor(PATTERN)
    c.setLineWidth(0.22)
    for y in range(28, int(PAGE_H - 26), 17):
        c.ellipse(30, y - 25, PAGE_W - 30, y + 25, fill=0, stroke=1)
    for x in range(40, int(PAGE_W - 35), 23):
        c.circle(x, PAGE_H / 2, 84 + x % 32, fill=0, stroke=1)


def border(c):
    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    c.roundRect(10, 10, PAGE_W - 20, PAGE_H - 20, 10, fill=0, stroke=1)
    c.setLineWidth(0.45)
    c.roundRect(16, 16, PAGE_W - 32, PAGE_H - 32, 7, fill=0, stroke=1)
    for x in range(18, int(PAGE_W - 17), 9):
        c.circle(x, 16, 4, fill=0, stroke=1)
        c.circle(x, PAGE_H - 16, 4, fill=0, stroke=1)
    for y in range(22, int(PAGE_H - 20), 9):
        c.circle(16, y, 4, fill=0, stroke=1)
        c.circle(PAGE_W - 16, y, 4, fill=0, stroke=1)


def seal(c, cx, cy, radius, label):
    c.setFillColor(HexColor("#E2E9DB"))
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.circle(cx, cy, radius, fill=1, stroke=1)
    c.circle(cx, cy, radius - 4, fill=0, stroke=1)
    c.circle(cx, cy, radius - 10, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 5.2)
    c.setFillColor(INK)
    c.drawCentredString(cx, cy + 1, label)
    c.setFont("Helvetica", 3.8)
    c.drawCentredString(cx, cy - 7, "SAMPLE")


def decorative_bars(c, x, y, width, height, seed=0):
    """Fill the area with meaningless bars when there is nothing to encode."""
    c.setFillColor(INK)
    cursor = x
    index = 0
    while cursor < x + width:
        bar = 0.7 + ((index * 5 + seed) % 4) * 0.45
        c.rect(cursor, y, bar, height, fill=1, stroke=0)
        cursor += bar + (0.65 if index % 2 else 1.25)
        index += 1


def barcode(c, x, y, width, height, seed=0, value=None):
    """Draw a scannable Code 128 symbol for `value`, scaled to span `width`.

    The symbol is measured at a unit module width, then rebuilt with the module
    width that makes it exactly `width` points wide, quiet zones included.
    """
    text = "".join(ch for ch in str(value or "").upper() if ch in BARCODE_CHARSET)
    if not text:
        decorative_bars(c, x, y, width, height, seed)
        return

    probe = code128.Code128(
        text,
        barWidth=1,
        barHeight=height,
        humanReadable=False,
        quiet=True,
        lquiet=QUIET_MODULES,
        rquiet=QUIET_MODULES,
    )
    if probe.width <= 0:
        decorative_bars(c, x, y, width, height, seed)
        return

    module = width / probe.width
    symbol = code128.Code128(
        text,
        barWidth=module,
        barHeight=height,
        humanReadable=False,
        quiet=True,
        lquiet=QUIET_MODULES * module,
        rquiet=QUIET_MODULES * module,
    )
    # Blank the page pattern behind the symbol so the quiet zones stay clean.
    c.setFillColor(PAPER)
    c.rect(x - 2, y - 2, width + 4, height + 4, fill=1, stroke=0)
    c.setFillColor(INK)
    symbol.drawOn(c, x, y)


def header(c, details, results):
    seal(c, 54, 790, 27, "JNTUH")
    seal(c, 558, 790, 30, "SAMPLE")
    fit(
        c,
        "JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY HYDERABAD",
        95,
        812,
        422,
        13,
        True,
        "center",
    )
    fit(
        c,
        "HYDERABAD - 500 085, TELANGANA STATE, INDIA",
        132,
        796,
        348,
        9.5,
        True,
        "center",
    )
    c.setFillColor(INK)
    c.roundRect(190, 774, 242, 15, 7, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 7.2)
    c.drawCentredString(311, 779, "CONSOLIDATED MEMO OF MARKS / GRADES AND CREDITS")
    roll_number = str(details.get("rollNumber", "") or "")
    barcode(c, 82, 756, 98, 18, 3, roll_number)
    fit(c, roll_number or "CMM-SAMPLE", 82, 746, 98, 7, True, "center")
    fit(c, "B.Tech.", 185, 755, 44, 8, True)
    fit(c, details.get("branch", ""), 232, 755, 310, 8.5, True)

    rows = [
        ("Name", details.get("name", "")),
        ("Hall Ticket No.", details.get("rollNumber", "")),
        ("Father Name", details.get("fatherName", "")),
        ("College Code", details.get("collegeCode", "")),
    ]
    for idx, (label, value) in enumerate(rows):
        yy = 735 - idx * 15
        fit(c, label, 88, yy, 80, 6.8, True)
        fit(c, ":", 169, yy, 6, 6.8, True)
        fit(c, value, 176, yy, 224, 7, True)

    right = [
        ("Document", "CMM SAMPLE"),
        ("Credits Secured", f"{float(results.get('credits', 0)):g}"),
        ("Aggregate CGPA", results.get("CGPA", "—")),
    ]
    for idx, (label, value) in enumerate(right):
        yy = 735 - idx * 18
        fit(c, label, 415, yy, 82, 6.4, True)
        fit(c, ":", 499, yy, 6, 6.4, True)
        fit(c, value, 507, yy, 76, 6.6, True)


def vertical_label(c, text, cx, cy, size=5.2):
    c.saveState()
    c.translate(cx, cy)
    c.rotate(90)
    c.setFont("Helvetica-Bold", size)
    c.setFillColor(INK)
    c.drawCentredString(0, -2, text)
    c.restoreState()


def columns(c, x0, y_top, y_bottom, draw_titles=False):
    widths = [48, 174, 18, 18, 24]
    bounds = [x0]
    for width in widths:
        bounds.append(bounds[-1] + width)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.55)
    for xx in bounds:
        c.line(xx, y_top, xx, y_bottom)
    if draw_titles:
        fit(c, "SUBJECT CODE", bounds[0], y_bottom + 10, widths[0], 4.8, True, "center")
        fit(c, "SUBJECT TITLE", bounds[1], y_bottom + 10, widths[1], 7, True, "center")
        vertical_label(c, "GRADE POINT", bounds[2] + widths[2] / 2, y_bottom + 16, 4.1)
        vertical_label(c, "GRADE", bounds[3] + widths[3] / 2, y_bottom + 16)
        vertical_label(c, "CREDITS", bounds[4] + widths[4] / 2, y_bottom + 16)
    return bounds


def semester_rows(c, semester, bounds, top, bottom, max_rows=11):
    subjects = (semester or {}).get("subjects", [])[:max_rows]
    row_h = (top - bottom) / max_rows
    for row_index, subject in enumerate(subjects, 1):
        yy = top - row_index * row_h + row_h * 0.34
        grade = str(subject.get("grades", "-")).upper()
        fit(c, subject.get("subjectCode", ""), bounds[0] + 2, yy, bounds[1] - bounds[0] - 4, 5.2, align="center")
        fit(c, subject.get("subjectName", ""), bounds[1] + 5, yy, bounds[2] - bounds[1] - 9, 5.25)
        fit(c, GRADE_POINTS.get(grade, "-"), bounds[2], yy, bounds[3] - bounds[2], 5.5, align="center")
        fit(c, grade, bounds[3], yy, bounds[4] - bounds[3], 5.5, True, "center")
        fit(c, f"{float(subject.get('credits', 0)):.1f}", bounds[4], yy, bounds[5] - bounds[4], 5.5, align="center")


def academic_table(c, results):
    semesters = {str(item.get("semester")): item for item in results.get("semesters", [])}
    left_x, right_x, half_w = 24, 306, 282
    table_top, header_h = 684, 34
    c.setFillColor(HexColor("#E3E8DE"))
    c.setStrokeColor(LINE)
    c.rect(left_x, table_top - header_h, half_w * 2, header_h, fill=1, stroke=1)
    columns(c, left_x, table_top, table_top - header_h, True)
    columns(c, right_x, table_top, table_top - header_h, True)

    blocks = [
        ("I YEAR", "1-1", "1-2", 650, 520),
        ("II YEAR", "2-1", "2-2", 520, 390),
        ("III YEAR", "3-1", "3-2", 390, 260),
        ("IV YEAR", "4-1", "4-2", 260, 142),
    ]
    for year, left_sem, right_sem, top, bottom in blocks:
        band_h = 14
        c.setFillColor(HexColor("#E7EBE2"))
        c.setStrokeColor(LINE)
        c.rect(left_x, top - band_h, half_w * 2, band_h, fill=1, stroke=1)
        fit(c, "I SEMESTER", left_x, top - 10, half_w, 6.6, True, "center")
        fit(c, year, left_x + half_w - 42, top - 10, 84, 6.6, True, "center")
        fit(c, "II SEMESTER", right_x, top - 10, half_w, 6.6, True, "center")
        data_top = top - band_h
        c.rect(left_x, bottom, half_w * 2, data_top - bottom, fill=0, stroke=1)
        left_bounds = columns(c, left_x, data_top, bottom)
        right_bounds = columns(c, right_x, data_top, bottom)
        semester_rows(c, semesters.get(left_sem), left_bounds, data_top, bottom)
        semester_rows(c, semesters.get(right_sem), right_bounds, data_top, bottom)


def footer(c, details, results):
    credits_label = "Number of Credits registered and secured are:"
    cgpa_label = "Aggregate Marks / CGPA Secured:"
    c.setFillColor(INK)
    c.setFont("Helvetica", 7)
    c.drawString(38, 113, credits_label)
    credits_x = 38 + stringWidth(credits_label, "Helvetica", 7) + 5
    c.setFont("Helvetica-Bold", 8)
    c.drawString(credits_x, 113, f"{float(results.get('credits', 0)):g}")
    c.setFont("Helvetica", 7)
    c.drawString(38, 95, cgpa_label)
    cgpa_x = 38 + stringWidth(cgpa_label, "Helvetica", 7) + 5
    c.setFont("Helvetica-Bold", 8)
    c.drawString(cgpa_x, 95, str(results.get("CGPA", "—")))
    fit(c, "Date of Issue", 38, 77, 72, 7)
    fit(c, "—", 112, 77, 150, 8)
    # Kept clear of the gold seal dot at (313, 95); overprint would break the scan.
    barcode(c, 267, 62, 140, 22, 11, details.get("rollNumber"))
    c.setFillColor(GOLD)
    c.circle(313, 95, 8, fill=1, stroke=0)
    fit(c, "CONTROLLER OF EXAMINATIONS", 418, 76, 164, 7.2, True, "center")
    fit(c, "(No signature shown — sample illustration)", 405, 62, 188, 5.2, align="center")
    fit(c, "jntuhconnect.dhethi.com", 206, 49, 200, 6.5, True, "center")
    c.linkURL(
        "https://jntuhconnect.dhethi.com",
        (206, 45, 406, 57),
        relative=0,
        thickness=0,
    )
    fit(c, "SAMPLE DOCUMENT — NOT VALID FOR VERIFICATION OR OFFICIAL USE", 130, 35, 352, 5.4, True, "center")


def generate_cmm_pdf(
    payload: Mapping[str, Any], output_path: str | Path | None = None
) -> bytes:
    """Generate a CMM sample PDF as bytes and optionally write it to disk."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping containing details and results")
    details = payload.get("details", {})
    results = payload.get("results", {})
    if not isinstance(details, Mapping) or not isinstance(results, Mapping):
        raise ValueError("payload.details and payload.results must be objects")
    if not isinstance(results.get("semesters", []), list):
        raise ValueError("payload.results.semesters must be an array")

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    c.setTitle(f"CMM Sample — {details.get('rollNumber', 'Illustration')}")
    c.setAuthor("Generated illustration; not an official academic credential")
    background(c)
    border(c)
    header(c, details, results)
    academic_table(c, results)
    footer(c, details, results)
    c.showPage()
    c.save()
    pdf_bytes = buffer.getvalue()

    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(pdf_bytes)
    return pdf_bytes
