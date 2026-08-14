from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_invoice_pdf(invoice, debtor, username):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=24, spaceAfter=20, textColor=colors.HexColor('#2c3e50'))
    elements.append(Paragraph("<b>YourInboxHero</b> - Invoice", title_style))
    elements.append(Spacer(1, 12))

    # Details
    normal_style = styles["Normal"]
    elements.append(Paragraph(f"<b>Invoice Number:</b> {invoice.invoice_number}", normal_style))
    elements.append(Paragraph(f"<b>Due Date:</b> {invoice.due_date}", normal_style))
    elements.append(Paragraph(f"<b>Status:</b> {invoice.status.capitalize()}", normal_style))
    elements.append(Spacer(1, 20))

    # Parties
    elements.append(Paragraph(f"<b>From:</b> {username}", normal_style))
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
        ('GRID', (0,0), (-1,-1), 1, colors.black)
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
