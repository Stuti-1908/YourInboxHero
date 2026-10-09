"""Invoice PDF generation.

Layout follows standard B2B invoice conventions (big "INVOICE" header,
invoice number/dates grouped top-right, From/Bill To two-column block,
itemized table with subtotal distinct from total, payment instructions
at the bottom) rather than a flat list of labeled fields -- see the
module's companion research in the M-whatever commit message for the
specific references this was checked against.
"""
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT

import base64
from reportlab.platypus import Image

from src.services.plan_features import plan_has_feature

# Palette: a single dark ink color for structure/headings, plus one
# status color per invoice state so "Overdue" reads as urgent and
# "Paid" reads as settled, not just a plain label like every other row.
_INK = colors.HexColor('#111827')
_MUTED = colors.HexColor('#6b7280')
_LINE = colors.HexColor('#e5e7eb')
_PANEL_BG = colors.HexColor('#f9fafb')

_STATUS_COLORS = {
    "upcoming": colors.HexColor('#2563eb'),
    "due": colors.HexColor('#d97706'),
    "overdue": colors.HexColor('#dc2626'),
    "paid": colors.HexColor('#16a34a'),
    "manual": colors.HexColor('#6b7280'),
    "paused": colors.HexColor('#6b7280'),
}


def _status_value(status) -> str:
    return status.value if hasattr(status, 'value') else str(status)


def generate_invoice_pdf(invoice, debtor, user):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    elements = []

    brand_name = user.company_name or user.username
    status_str = _status_value(invoice.status)
    status_color = _STATUS_COLORS.get(status_str, _MUTED)
    amount_str = f"${float(invoice.amount):,.2f}"

    normal = ParagraphStyle('Normal2', parent=styles['Normal'], fontSize=9.5, textColor=_INK, leading=13)
    muted = ParagraphStyle('Muted', parent=normal, textColor=_MUTED, fontSize=8.5)
    label = ParagraphStyle('Label', parent=muted, fontSize=8, textColor=_MUTED)
    label_r = ParagraphStyle('LabelRight', parent=label, alignment=TA_RIGHT)
    value_r = ParagraphStyle('ValueRight', parent=normal, alignment=TA_RIGHT)
    heading = ParagraphStyle('SectionHeading', parent=normal, fontSize=8, textColor=_MUTED, fontName='Helvetica-Bold')

    # ---- Header row: logo/brand name (left) vs "INVOICE" + status (right) ----
    has_branding = plan_has_feature(user.subscription_plan, "custom_branding")
    left_header_cell = None
    if user.logo_base64 and has_branding:
        try:
            header_prefix, encoded = user.logo_base64.split(",", 1) if "," in user.logo_base64 else ("", user.logo_base64)
            img_buffer = BytesIO(base64.b64decode(encoded))
            img = Image(img_buffer, width=140, height=46, kind='proportional')
            img.hAlign = 'LEFT'
            left_header_cell = img
        except Exception:
            left_header_cell = None
    if left_header_cell is None:
        left_header_cell = Paragraph(
            f"<font size=15 color='#111827'><b>{brand_name}</b></font>", normal
        )

    invoice_title_style = ParagraphStyle(
        'InvoiceTitle', parent=styles['Normal'], fontSize=26, leading=30, textColor=_INK,
        fontName='Helvetica-Bold', alignment=TA_RIGHT,
    )
    status_style = ParagraphStyle(
        'StatusBadge', parent=normal, alignment=TA_RIGHT, fontName='Helvetica-Bold',
        fontSize=9, textColor=status_color,
    )
    right_header_cell = [
        Paragraph("INVOICE", invoice_title_style),
        Spacer(1, 8),
        Paragraph(status_str.upper(), status_style),
    ]

    header_table = Table([[left_header_cell, right_header_cell]], colWidths=[3.2 * inch, 3.2 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1, color=_LINE))
    elements.append(Spacer(1, 18))

    # ---- From / Bill To (left) vs Invoice #, issue date, due date (right) ----
    created_at = getattr(invoice, 'created_at', None)
    issue_date_str = str(created_at.date() if hasattr(created_at, 'date') else created_at) if created_at else "—"

    from_block = [
        Paragraph("FROM", heading),
        Spacer(1, 3),
        Paragraph(f"<b>{brand_name}</b>", normal),
    ]
    bill_to_block = [
        Paragraph("BILL TO", heading),
        Spacer(1, 3),
        Paragraph(f"<b>{debtor.name}</b>", normal),
        Paragraph(debtor.email, muted),
    ]
    if getattr(debtor, 'phone', None):
        bill_to_block.append(Paragraph(debtor.phone, muted))

    left_meta_cell = from_block + [Spacer(1, 12)] + bill_to_block

    meta_rows = [
        [Paragraph("Invoice Number", label_r), Paragraph(invoice.invoice_number, value_r)],
        [Paragraph("Issue Date", label_r), Paragraph(issue_date_str, value_r)],
        [Paragraph("Due Date", label_r), Paragraph(str(invoice.due_date), value_r)],
    ]
    meta_table = Table(meta_rows, colWidths=[1.6 * inch, 1.6 * inch])
    meta_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    meta_outer = Table([[left_meta_cell, meta_table]], colWidths=[3.6 * inch, 2.8 * inch])
    meta_outer.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(meta_outer)
    elements.append(Spacer(1, 24))

    # ---- Line items ----
    item_header_style = ParagraphStyle('ItemHeader', parent=normal, fontName='Helvetica-Bold', fontSize=8.5, textColor=_MUTED)
    item_header_style_r = ParagraphStyle('ItemHeaderR', parent=item_header_style, alignment=TA_RIGHT)
    description_text = invoice.description or "Services rendered"

    items_data = [
        [Paragraph("DESCRIPTION", item_header_style), Paragraph("AMOUNT", item_header_style_r)],
        [Paragraph(description_text, normal), Paragraph(amount_str, value_r)],
    ]
    items_table = Table(items_data, colWidths=[4.6 * inch, 1.8 * inch])
    items_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 1, _INK),
        ('LINEBELOW', (0, 1), (-1, 1), 0.5, _LINE),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 6))

    # ---- Subtotal / Total summary, right-aligned ----
    summary_label = ParagraphStyle('SummaryLabel', parent=normal, alignment=TA_RIGHT, textColor=_MUTED, fontSize=9.5)
    summary_value = ParagraphStyle('SummaryValue', parent=normal, alignment=TA_RIGHT, fontSize=9.5)
    total_label = ParagraphStyle('TotalLabel', parent=normal, alignment=TA_RIGHT, fontName='Helvetica-Bold', fontSize=12)
    total_value = ParagraphStyle('TotalValue', parent=normal, alignment=TA_RIGHT, fontName='Helvetica-Bold', fontSize=16, textColor=_INK)

    summary_rows = [
        [Paragraph("Subtotal", summary_label), Paragraph(amount_str, summary_value)],
        [Paragraph("Total Due", total_label), Paragraph(amount_str, total_value)],
    ]
    summary_table = Table(summary_rows, colWidths=[4.6 * inch, 1.8 * inch])
    summary_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING', (0, 1), (-1, 1), 8),
        ('LINEABOVE', (0, 1), (-1, 1), 1, _INK),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 28))

    # ---- Payment link / instructions ----
    if invoice.payment_link:
        link_style = ParagraphStyle('PayLink', parent=normal, textColor=colors.HexColor('#2563eb'))
        elements.append(Paragraph("PAYMENT LINK", heading))
        elements.append(Spacer(1, 3))
        elements.append(Paragraph(f'<link href="{invoice.payment_link}">{invoice.payment_link}</link>', link_style))
        elements.append(Spacer(1, 16))

    if invoice.payment_instructions:
        elements.append(Paragraph("PAYMENT INSTRUCTIONS", heading))
        elements.append(Spacer(1, 3))
        elements.append(Paragraph(invoice.payment_instructions, normal))
        elements.append(Spacer(1, 16))

    # ---- Footer ----
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=_LINE))
    elements.append(Spacer(1, 8))
    footer_style = ParagraphStyle('Footer', parent=muted, fontSize=8, alignment=TA_LEFT)
    elements.append(Paragraph(f"Questions about this invoice? Contact {brand_name}.", footer_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
