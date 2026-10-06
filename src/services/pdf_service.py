from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import base64
from reportlab.platypus import Image

from src.services.plan_features import plan_has_feature


def generate_invoice_pdf(invoice, debtor, user):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=24, spaceAfter=20, textColor=colors.HexColor('#2c3e50'))

    # Custom branding (logo) is a Growth+ feature. A Starter user can still
    # save a logo in Settings — it's just not applied until they upgrade,
    # so nothing needs re-entering once they do.
    has_branding = plan_has_feature(user.subscription_plan, "custom_branding")
    if user.logo_base64 and has_branding:
        try:
            # Handle data URL format (e.g. data:image/png;base64,...)
            header, encoded = user.logo_base64.split(",", 1) if "," in user.logo_base64 else ("", user.logo_base64)
            img_data = base64.b64decode(encoded)
            img_buffer = BytesIO(img_data)
            # Use ReportLab Image
            img = Image(img_buffer, width=150, height=50, kind='proportional')
            img.hAlign = 'LEFT'
            elements.append(img)
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("<b>Invoice</b>", title_style))
        except Exception:
            brand_name = user.company_name or user.username
            elements.append(Paragraph(f"<b>{brand_name}</b> - Invoice", title_style))
    else:
        brand_name = user.company_name or user.username
        elements.append(Paragraph(f"<b>{brand_name}</b> - Invoice", title_style))

    elements.append(Spacer(1, 12))

    # Details
    normal_style = styles["Normal"]
    elements.append(Paragraph(f"<b>Invoice Number:</b> {invoice.invoice_number}", normal_style))
    elements.append(Paragraph(f"<b>Due Date:</b> {invoice.due_date}", normal_style))
    elements.append(Paragraph(f"<b>Status:</b> {invoice.status.capitalize()}", normal_style))
    elements.append(Spacer(1, 20))

    # Parties
    elements.append(Paragraph(f"<b>From:</b> {user.company_name or user.username}", normal_style))
    elements.append(Paragraph(f"<b>To:</b> {debtor.name} ({debtor.email})", normal_style))
    elements.append(Spacer(1, 20))

    # Table
    data = [
        ["Description", "Amount"],
        [invoice.description or "Invoice Amount", f"${invoice.amount}"]
    ]

    t = Table(data, colWidths=[300, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # Total
    total_style = ParagraphStyle('TotalStyle', parent=styles['Heading2'], alignment=2)
    elements.append(Paragraph(f"<b>Total:</b> ${invoice.amount}", total_style))
    elements.append(Spacer(1, 30))

    # Payment Instructions
    if invoice.payment_instructions:
        elements.append(Paragraph("<b>Payment Instructions:</b>", styles['Heading3']))
        elements.append(Paragraph(invoice.payment_instructions, normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
