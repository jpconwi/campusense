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
