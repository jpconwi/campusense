"""
services/pdf_service.py - builds the PDF reports (ReportLab).

Same look as the original faculty report: "CampusSense AI" heading,
report title, label/value lines and a small footer.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


def generate_pdf(path, title, rows):
    """rows = list of (label, value) pairs."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    left, value_x, right = 60, 190, width - 60
    y = height - 70

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(left, y, "CampusSense AI")
    y -= 22
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left, y, "NEMSU Tandag Main Campus")
    y -= 33
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(left, y, title)
    y -= 45

    for label, value in rows:
        lines = simpleSplit(str(value or "-"), "Helvetica", 11, right - value_x) or ["-"]
        if y - 18 * len(lines) < 80:          # start a new page when full
            pdf.showPage()
            y = height - 70
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(left, y, f"{label}:")
        pdf.setFont("Helvetica", 11)
        for line in lines:
            pdf.drawString(value_x, y, line)
            y -= 18
        y -= 12

    y -= 10
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(left, max(y, 50), "Generated automatically by CampusSense AI.")
    pdf.save()


# ---------------------------------------------------------------------------
# On Render (and most hosts) the disk is wiped on every deploy/restart, but the
# database is kept. So a PDF that is missing on disk is simply drawn again from
# its database row the next time someone opens it.
def _rows_for(kind, r):
    if kind == "concerns":
        return "Campus Concern Report", [
            ("Concern ID", r["id"]), ("Name", r["reporter_name"]), ("Email", r["reporter_email"]),
            ("Location", r["location"]), ("Room", r["room"] or "-"),
            ("Concern Type", r["concern_type"]), ("Description", r["description"]),
            ("Date", r["concern_date"]), ("Submitted At", r["created_at"]),
            ("Status", r["status"])]
    if kind == "reports":
        return "Campus Report", [
            ("Report ID", r["id"]), ("Reporter", r["reporter_name"]), ("Email", r["reporter_email"]),
            ("Location", r["location"]), ("Area", r["area"] or "-"), ("Room", r["room"] or "-"),
            ("Report Type", r["report_type"]), ("Description", r["description"]),
            ("Date", r["report_date"]), ("Submitted At", r["created_at"]),
            ("Status", r["status"])]
    if kind == "feedback":
        return "Campus Feedback", [
            ("Feedback ID", r["id"]), ("Name", r["name"]), ("Email", r["email"]),
            ("Area / Facility", r["area"]), ("Feedback Type", r["feedback_type"]),
            ("Message", r["message"]), ("Date", r["feedback_date"]),
            ("Submitted At", r["created_at"]), ("Status", r["status"])]
    return "Faculty Availability Report", [          # faculty
        ("Report ID", r["display_id"]), ("Instructor", r["instructor"]),
        ("Reason", r["reason"]), ("Date of Absence", r["start_date"]),
        ("Expected Return", r["expected_return"]),
        ("Submitted At", r["submitted_at"]), ("Status", r["status"])]


def ensure_pdf(kind, row, path):
    """Make sure the PDF file exists; draw it again from `row` if the disk lost it."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        title, rows = _rows_for(kind, row)
        generate_pdf(path, title, rows)
