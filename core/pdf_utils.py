"""
pdf_utils.py — Shared premium PDF styling for Mastan Catering.
All in-app attendance PDF downloads call build_attendance_pdf().
"""
import os
from io import BytesIO
from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from reportlab.platypus import Image as RLImage

# ── Logo path ─────────────────────────────────────────────────────────────────
_LOGO_PATH = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')

# ── Brand colours ─────────────────────────────────────────────────────────────
DARK_BG   = colors.HexColor('#16213e')
GOLD      = colors.HexColor('#d4a852')
WHITE     = colors.white
GREEN     = colors.HexColor('#2ecc85')
RED       = colors.HexColor('#e05c5c')
GREY_TEXT = colors.HexColor('#444444')
CREAM     = colors.HexColor('#f9f6f1')
LINE      = colors.HexColor('#e0d9ce')
TOTAL_BG  = colors.HexColor('#fdf9f3')

# ── Landscape letter usable width = 792 - 44 (margins) = 748 pt ──────────────
PAGE_W = 748

# Staff table column widths — summed exactly to PAGE_W (748)
# StaffID | Name | Phone | Level | Arrival | Late | Shoes | Uniform | Grooming | Paid | Wage
COL_W = [76, 154, 110, 78, 60, 38, 38, 46, 32, 40, 76]
# total = 76+154+110+78+60+38+38+46+32+40+76 = 748


def _p(text, size=9, bold=False, color=GREY_TEXT, align=0):
    """Quick Paragraph helper."""
    font = 'Helvetica-Bold' if bold else 'Helvetica'
    style = ParagraphStyle(
        f'_p_{size}_{bold}_{align}',
        fontName=font, fontSize=size,
        textColor=color, alignment=align,
        leading=size * 1.3, spaceAfter=0, spaceBefore=0,
    )
    return Paragraph(text, style)


def _tick():
    return _p('<font name="ZapfDingbats" color="#2ecc85" size="11">4</font>', size=9)


def _cross():
    return _p('<font color="#e05c5c" size="8"><b>-30</b></font>', size=9)


def _build_header(booking):
    """Return a Table that forms the dark branded header block."""

    # ── Left side: text ───────────────────────────────────────────────────────
    left = [
        _p('MASTAN CATERING &amp; SERVICES', size=7, bold=True, color=GOLD),
        Spacer(1, 3),
        _p('Event Attendance Report', size=16, bold=True, color=WHITE),
        Spacer(1, 3),
        _p(f'Report ID: ATT-{booking.pk:04d}', size=9, color=colors.HexColor('#9ba3ba')),
    ]

    # ── Right side: logo + generated time ─────────────────────────────────────
    date_str = timezone.now().strftime('%d %b %Y  ·  %I:%M %p')
    right_items = [_p(date_str, size=8, color=colors.HexColor('#9ba3ba'), align=2)]
    if os.path.exists(_LOGO_PATH):
        logo = RLImage(_LOGO_PATH, width=46, height=46)
        right_items.append(logo)

    left_col  = [[item] for item in left]
    right_col = [[item] for item in right_items]

    hdr = Table([[left, right_items]], colWidths=[PAGE_W * 0.66, PAGE_W * 0.34])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), DARK_BG),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (1, 0), (1, -1),  'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING',   (0, 0), (-1, -1), 18),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 18),
    ]))
    return hdr


def _build_info_strip(booking):
    """Full-width 4-cell info strip below header."""

    def cell(label, val):
        return [
            _p(label, size=7, bold=True, color=colors.HexColor('#a0a8bb')),
            Spacer(1, 3),
            _p(str(val), size=9, bold=True, color=DARK_BG),
        ]

    w = PAGE_W / 4
    row_data = [[
        cell('CLIENT',     booking.name),
        cell('EVENT TYPE', booking.get_event_type_display()),
        cell('EVENT DATE', booking.event_date.strftime('%d %B %Y')),
        cell('VENUE',      booking.venue or 'N/A'),
    ]]
    t = Table(row_data, colWidths=[w, w, w, w])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), CREAM),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 18),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LINEAFTER',     (0, 0), (2, -1),  0.5, LINE),
        ('BOX',           (0, 0), (-1, -1), 0.5, LINE),
    ]))
    return t


def _build_staff_table(assigned_staff, attendance_map, applications_map):
    """Return (Table, total_wage) for all assigned staff."""

    headers = [
        'Staff ID', 'Full Name', 'Phone', 'Level',
        'Arrival', 'Late', 'Shoes', 'Uniform', 'Grooming', 'Paid', 'Wage (Rs)'
    ]
    hdr_row = [_p(h, size=8, bold=True, color=GOLD) for h in headers]
    data = [hdr_row]
    total_wage = 0

    for staff in assigned_staff:
        att        = attendance_map.get(staff.pk)
        raw_status = att.status if att else 'absent'
        r_time     = att.reaching_time.strftime('%I:%M %p') if att and att.reaching_time else '—'

        late_ok  = not att or getattr(att, 'on_time',  True)
        shoe_ok  = not att or getattr(att, 'shoes',    True)
        unif_ok  = not att or getattr(att, 'uniform',  True)
        groom_ok = not att or getattr(att, 'grooming', True)

        penalty = sum([
            0 if late_ok  else 30,
            0 if shoe_ok  else 30,
            0 if unif_ok  else 30,
            0 if groom_ok else 30,
        ])
        
        bonus_val = float(att.bonus) if att and getattr(att, 'bonus', 0) else 0.0
        deduction_val = float(att.deduction) if att and getattr(att, 'deduction', 0) else 0.0
        
        wage = float(staff.daily_rate) + bonus_val - penalty - deduction_val
        if raw_status in ('present', 'half_day'):
            total_wage += wage
        else:
            wage = 0  # Absent staff aren't paid

        app   = applications_map.get(staff.pk)
        phone = staff.phone or '—'
        paid_p = _p('<font color="#2ecc85"><b>Yes</b></font>' if att and att.payment_given
                    else '<font color="#e05c5c">No</font>', size=9)

        # StaffID — prevent wrapping on hyphens by replacing with non-breaking hyphen
        sid = (staff.staff_id or '—').replace('-', '\u2011')

        if raw_status == 'absent':
            wage_display = _p('<font color="#e05c5c" size="9"><b>Absent</b></font>', size=9, bold=False, align=2)
            # If absent, make sure the ticks/crosses are shown as crosses and time as Absent.
            r_time = 'Absent'
        else:
            wage_details = [f'<b>Rs.{wage:,.0f}</b>']
            if bonus_val > 0:
                wage_details.append(f'<font size="7" color="#2ecc85">+{bonus_val:g} Bns</font>')
            if (penalty + deduction_val) > 0:
                wage_details.append(f'<font size="7" color="#e05c5c">-{penalty + deduction_val:g} Ded</font>')
            wage_display = _p('<br/>'.join(wage_details), size=9, bold=False, color=DARK_BG, align=2)

        data.append([
            _p(sid, size=8),
            _p(staff.full_name, size=8.5, bold=True, color=DARK_BG),
            _p(phone, size=8),
            _p(staff.get_level_display(), size=8),
            _p(r_time, size=8),
            _tick() if late_ok  else _cross(),
            _tick() if shoe_ok  else _cross(),
            _tick() if unif_ok  else _cross(),
            _tick() if groom_ok else _cross(),
            paid_p,
            wage_display,
        ])

    # Total row — label spans cols 0-9, value in col 10
    total_label = _p('<b>TOTAL WAGES PAYABLE</b>', size=9, bold=True, color=DARK_BG)
    total_val   = _p(f'<b>Rs.{total_wage:,}</b>', size=11, bold=True, color=DARK_BG, align=2)
    data.append([total_label, '', '', '', '', '', '', '', '', '', total_val])

    t = Table(data, colWidths=COL_W, repeatRows=1)
    t.setStyle(TableStyle([
        # ── Header row ────────────────────────────────────────────────────────
        ('BACKGROUND',    (0, 0),  (-1, 0),  DARK_BG),
        ('TOPPADDING',    (0, 0),  (-1, 0),  10),
        ('BOTTOMPADDING', (0, 0),  (-1, 0),  10),
        ('LEFTPADDING',   (0, 0),  (-1, 0),  8),
        ('RIGHTPADDING',  (0, 0),  (-1, 0),  8),
        ('ALIGN',         (0, 0),  (-1, 0),  'LEFT'),

        # ── Data rows ─────────────────────────────────────────────────────────
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [WHITE, CREAM]),
        ('TOPPADDING',    (0, 1),  (-1, -2), 8),
        ('BOTTOMPADDING', (0, 1),  (-1, -2), 8),
        ('LEFTPADDING',   (0, 1),  (-1, -2), 8),
        ('RIGHTPADDING',  (0, 1),  (-1, -2), 8),
        ('VALIGN',        (0, 0),  (-1, -2), 'MIDDLE'),
        ('LINEBELOW',     (0, 0),  (-1, -2), 0.4, LINE),
        ('BOX',           (0, 0),  (-1, -2), 0.5, LINE),

        # ── Total row ─────────────────────────────────────────────────────────
        ('SPAN',          (0, -1), (9, -1)),          # label spans cols 0-9
        ('BACKGROUND',    (0, -1), (-1, -1), TOTAL_BG),
        ('LINEABOVE',     (0, -1), (-1, -1), 2,   GOLD),
        ('LINEBELOW',     (0, -1), (-1, -1), 0.5, LINE),
        ('TOPPADDING',    (0, -1), (-1, -1), 11),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 11),
        ('LEFTPADDING',   (0, -1), (-1, -1), 12),
        ('RIGHTPADDING',  (0, -1), (-1, -1), 12),
        ('VALIGN',        (0, -1), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (-1, -1),(-1, -1), 'RIGHT'),
    ]))
    return t, total_wage


def _build_footer(total_wage):
    """Bottom summary bar + watermark line."""
    gen_str = timezone.now().strftime('%d %b %Y  ·  %I:%M %p')
    row = [[
        _p('TOTAL WAGES PAYABLE', size=8, bold=True, color=colors.HexColor('#aaa')),
        _p(f'<b>Rs. {total_wage:,}</b>', size=14, bold=True, color=DARK_BG),
        _p(f'Generated: {gen_str}', size=8, color=colors.HexColor('#bbb'), align=2),
    ]]
    t = Table(row, colWidths=[180, 200, PAGE_W - 380])
    t.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN',        (2, 0), (2, 0), 'RIGHT'),
    ]))
    return t


def build_attendance_pdf(booking, assigned_staff, attendance_map, applications_map, generated_by="System"):
    """
    Build and return a premium branded attendance PDF as a BytesIO buffer.

    Usage:
        buf = build_attendance_pdf(booking, assigned_staff, att_map, app_map)
        return HttpResponse(buf.getvalue(), content_type='application/pdf')
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=22, rightMargin=22,
        topMargin=22,  bottomMargin=22,
    )
    el = []

    # 1 — Dark branded header
    el.append(_build_header(booking))

    # 2 — Gold separator
    el.append(HRFlowable(width='100%', thickness=3,
                          color=GOLD, spaceAfter=0, spaceBefore=0))

    # 3 — Full-width info strip
    el.append(_build_info_strip(booking))
    el.append(Spacer(1, 14))

    # 4 — Staff attendance table
    staff_table, total_wage = _build_staff_table(assigned_staff, attendance_map, applications_map)
    el.append(staff_table)

    # 5 — Footer summary
    el.append(Spacer(1, 12))
    el.append(HRFlowable(width='100%', thickness=0.5,
                          color=LINE, spaceBefore=0, spaceAfter=8))
    el.append(_build_footer(total_wage))
    el.append(Spacer(1, 6))

    wm_style = ParagraphStyle('wm', fontName='Helvetica', fontSize=7,
                               textColor=colors.HexColor('#cccccc'), alignment=2)
    el.append(Paragraph("Mastan Catering &amp; Services — Confidential Internal Document", wm_style))

    doc.build(el)
    return buffer


def build_invoice_pdf(invoice_data):
    """
    Build a premium, minimal white-paper invoice PDF.
    invoice_data = {
        'inv_no': '...', 'date': '...',
        'bill_to': '...', 'contact': '...',
        'items': [{'name': '...', 'hsn': '...', 'qty': 0, 'price': 0}, ...]
    }
    """
    buffer = BytesIO()
    from reportlab.lib.pagesizes import A4
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=35, rightMargin=35,
        topMargin=35,  bottomMargin=35,
    )
    el = []
    
    # ── Header (Logo + Company) ───────────────────────────────────────────────
    logo_cell = ''
    if os.path.exists(_LOGO_PATH):
        logo_cell = RLImage(_LOGO_PATH, width=50, height=50)

    brand_p = _p("Mastan Catering &amp; Services", size=18, bold=True, color=GREY_TEXT)
    sub_p   = _p("Kondotty, Kerala  ·  6235240942", size=10, color=colors.grey)
    
    head_t = Table([[ [brand_p, Spacer(1,2), sub_p], logo_cell ]], colWidths=[400, 125])
    head_t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',  (1,0), (1,0),   'RIGHT'),
    ]))
    el.append(head_t)
    el.append(Spacer(1, 15))
    el.append(HRFlowable(width='100%', thickness=2, color=GOLD, spaceAfter=20))

    # ── Title & Meta ──────────────────────────────────────────────────────────
    title_p = _p("INVOICE", size=24, bold=True, color=GREY_TEXT)
    
    sn = invoice_data.get('site_name', '').strip()
    ed = invoice_data.get('event_date', '').strip()
    
    parts = []
    if sn: parts.append(f"Site / Event: {sn}")
    if ed: parts.append(f"Event Date: {ed}")
    site_str = f"<br/>{'   |   '.join(parts)}" if parts else ""
    
    num_p   = _p(f"No: {invoice_data.get('inv_no','—')}   |   Date: {invoice_data.get('date','—')}{site_str}", 
                 size=10, color=GREY_TEXT, align=2)
    
    meta_t = Table([[title_p, num_p]], colWidths=[260, 265])
    meta_t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LINEBELOW', (0,0), (-1,-1), 1, GOLD),
    ]))
    el.append(meta_t)
    el.append(Spacer(1, 15))

    # ── Bill To / From ────────────────────────────────────────────────────────
    def meta_cell(label, val, sub, align=0):
        return [
            _p(label, size=8, bold=True, color=GOLD, align=align),
            Spacer(1, 2),
            _p(val, size=12, bold=True, color=GREY_TEXT, align=align),
            _p(sub, size=10, color=colors.grey, align=align),
        ]

    bt_cell = meta_cell("BILL TO", invoice_data.get('bill_to','—').upper(), invoice_data.get('contact','—'))
    fr_cell = meta_cell("FROM", "MASTAN CATERING", "Kondotty, Kerala", align=2)
    
    addr_t = Table([[ bt_cell, fr_cell ]], colWidths=[260, 265])
    addr_t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    el.append(addr_t)
    el.append(Spacer(1, 25))

    # ── Items Table ───────────────────────────────────────────────────────────
    headers = ['#', 'Description', 'Qty', 'Rate (Rs)', 'Amount (Rs)']
    hdr_row = [_p(h, size=9, bold=True, color=colors.white) for h in headers]
    data = [hdr_row]
    
    total_amt = 0
    total_qty = 0
    for i, item in enumerate(invoice_data.get('items', [])):
        qty = float(item.get('qty') or 0)
        price = float(item.get('price') or 0)
        amt = qty * price
        total_amt += amt
        total_qty += qty
        
        data.append([
            _p(str(i+1), size=10, color=colors.grey),
            _p(item.get('name') or '—', size=11, bold=True),
            _p(f"{qty:g}", size=10),
            _p(f"{price:,.2f}", size=10, align=2),
            _p(f"{amt:,.2f}", size=11, bold=True, align=2),
        ])

    # Append a special row for quantity totals inside the main table
    # so it perfectly aligns under the "Qty" column.
    data.append([
        "",
        _p("TOTAL", size=8, bold=True, color=colors.grey, align=2),
        _p(f"{total_qty:g}", size=11, bold=True),
        "",
        _p(f"Rs. {total_amt:,.2f}", size=9, bold=True, color=colors.grey, align=2)
    ])

    tbl = Table(data, colWidths=[30, 285, 50, 75, 85], repeatRows=1)
    
    # Calculate row indices for item backgrounds (row 1 to second-to-last)
    last_item_idx = len(data) - 2 # data has header, items..., and quantity-total-row
    
    styles = [
        ('BACKGROUND', (0,0), (-1,0), GOLD),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        # Special styling for the quantity total row at the very bottom (index -1)
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, GOLD),
        ('TOPPADDING', (0,-1), (-1,-1), 10),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 10),
    ]
    
    if last_item_idx >= 1:
        styles.append(('ROWBACKGROUNDS', (0,1), (-1, last_item_idx), [colors.white, colors.HexColor('#fafafa')]))
        styles.append(('LINEBELOW', (0,0), (-1, last_item_idx), 0.5, colors.HexColor('#eeeeee')))
        
    tbl.setStyle(TableStyle(styles))
    el.append(tbl)
    
    # ── Total Row ─────────────────────────────────────────────────────────────
    # Standardized Grand Total block
    amt_str = f"Rs. {total_amt:,.2f}"
    
    total_label = _p('GRAND TOTAL', bold=True, size=10, color=colors.grey)
    total_val_p = _p(amt_str, size=14, bold=True, color=GOLD, align=2)

    tot_t = Table([[ total_label, total_val_p ]], colWidths=[340, 185])
    tot_t.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,0), 12),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
    ]))
    el.append(tot_t)
    el.append(Spacer(1, 40))
    
    # ── Footer ────────────────────────────────────────────────────────────────
    el.append(HRFlowable(width='100%', thickness=0.5, color=colors.lightgrey))
    footer_p = _p("Thank you for your business.", 
                  size=9, color=colors.grey, align=1)
    el.append(Spacer(1, 10))
    el.append(footer_p)

    doc.build(el)
    return buffer


def generate_financial_reports_pdf(reports, totals, month_name, year_filter, client_filter=''):
    """
    Premium financial reports PDF styled like the attendance PDF:
    dark header, gold separator, dark table with gold headers.
    """
    buffer = BytesIO()
    from reportlab.lib.pagesizes import landscape, A4
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=22, rightMargin=22,
        topMargin=22,  bottomMargin=22,
    )
    el = []
    FIN_W = 801  # landscape A4 usable = 841 - 22*2

    # 1 — Dark branded header
    date_str   = timezone.now().strftime('%d %b %Y  \u00b7  %I:%M %p')
    title_text = 'Financial Reports'
    if month_name or year_filter:
        title_text += f'  \u2014  {str(month_name).upper()} {str(year_filter)}'.strip()
    if client_filter:
        title_text += f' ({client_filter})'

    left = [
        _p("MASTAN CATERING &amp; SERVICES", size=7, bold=True, color=GOLD),
        Spacer(1, 3),
        _p(title_text, size=16, bold=True, color=WHITE),
        Spacer(1, 3),
        _p('Manual Financial Summary Report', size=9, color=colors.HexColor('#9ba3ba')),
    ]
    right_items = [_p(date_str, size=8, color=colors.HexColor('#9ba3ba'), align=2)]
    if os.path.exists(_LOGO_PATH):
        right_items.append(RLImage(_LOGO_PATH, width=46, height=46))

    hdr = Table([[left, right_items]], colWidths=[FIN_W * 0.66, FIN_W * 0.34])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), DARK_BG),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (1, 0), (1, -1),  'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING',   (0, 0), (-1, -1), 18),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 18),
    ]))
    el.append(hdr)

    # 2 — Gold separator
    el.append(HRFlowable(width='100%', thickness=3, color=GOLD, spaceAfter=0, spaceBefore=0))

    # 3 — Data starts directly after header
    reports_list = list(reports)
    t_boys     = totals.get('t_boys') or 0
    t_bill     = float(totals.get('t_bill') or 0)
    t_received = float(totals.get('t_received') or 0)
    t_profit   = float(totals.get('t_profit') or 0)
    el.append(Spacer(1, 14))

    # 4 — Main data table (col widths sum = 797)
    COL_FIN = [22, 55, 106, 126, 35, 78, 70, 70, 62, 58, 68, 47]
    headers  = ['SL','DATE','SITE NAME','EVENT NAME','BOYS',
                'INCHARGE','BILL (Rs)','RECEIVED (Rs)','PAID ON','PENDING','PROFIT','SETTLED']
    data = [[_p(h, size=8, bold=True, color=GOLD) for h in headers]]

    for i, r in enumerate(reports_list):
        paid_on   = r.payment_received_on.strftime('%d %b %Y') if r.payment_received_on else '\u2014'
        settled_p = _p(
            '<font color="#2ecc85"><b>YES</b></font>' if r.is_settled
            else '<font color="#e05c5c">NO</font>', size=8
        )
        pending = float(r.pending_amount or 0)
        profit  = float(r.profit or 0)
        data.append([
            _p(str(i+1), size=8, color=colors.HexColor('#999')),
            _p(r.event_date.strftime('%d-%m-%Y') if r.event_date else '\u2014', size=8),
            _p(r.site_name or '\u2014', size=8, bold=True, color=DARK_BG),
            _p(r.event_name or '\u2014', size=8),
            _p(str(r.boys_count or 0), size=8),
            _p(r.bill_incharge or '\u2014', size=8),
            _p(f'{float(r.bill_amount or 0):,.0f}', size=9, bold=True, color=DARK_BG),
            _p(f'{float(r.amount_received or 0):,.0f}', size=9, bold=True,
               color=colors.HexColor('#2ecc85')),
            _p(paid_on, size=8),
            _p(f'{pending:,.0f}' if pending else '\u2014', size=8,
               color=colors.HexColor('#e67e22') if pending else GREY_TEXT),
            _p(f'{profit:,.0f}', size=9, bold=True,
               color=colors.HexColor('#2ecc85') if profit >= 0 else RED),
            settled_p,
        ])

    data.append([
        _p('<b>TOTALS</b>', size=9, bold=True, color=DARK_BG), '', '', '',
        _p(f'<b>{t_boys}</b>', size=9, bold=True), '',
        _p(f'<b>{t_bill:,.0f}</b>', size=10, bold=True, color=DARK_BG),
        _p(f'<b>{t_received:,.0f}</b>', size=10, bold=True, color=DARK_BG),
        '', '',
        _p(f'<b>{t_profit:,.0f}</b>', size=10, bold=True,
           color=colors.HexColor('#2ecc85')), '',
    ])

    tbl = Table(data, colWidths=COL_FIN, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),  (-1, 0),  DARK_BG),
        ('TOPPADDING',    (0, 0),  (-1, 0),  9),
        ('BOTTOMPADDING', (0, 0),  (-1, 0),  9),
        ('LEFTPADDING',   (0, 0),  (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0),  (-1, -1), 6),
        ('ROWBACKGROUNDS',(0, 1),  (-1, -2), [WHITE, CREAM]),
        ('TOPPADDING',    (0, 1),  (-1, -2), 7),
        ('BOTTOMPADDING', (0, 1),  (-1, -2), 7),
        ('VALIGN',        (0, 0),  (-1, -2), 'MIDDLE'),
        ('LINEBELOW',     (0, 0),  (-1, -2), 0.4, LINE),
        ('BOX',           (0, 0),  (-1, -2), 0.5, LINE),
        ('SPAN',          (0, -1), (3, -1)),
        ('BACKGROUND',    (0, -1), (-1, -1), TOTAL_BG),
        ('LINEABOVE',     (0, -1), (-1, -1), 2,   GOLD),
        ('LINEBELOW',     (0, -1), (-1, -1), 0.5, LINE),
        ('TOPPADDING',    (0, -1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
        ('VALIGN',        (0, -1), (-1, -1), 'MIDDLE'),
    ]))
    el.append(tbl)

    # 5 — Footer
    el.append(Spacer(1, 14))
    el.append(HRFlowable(width='100%', thickness=0.5, color=LINE))
    el.append(Spacer(1, 6))
    gen_str = timezone.now().strftime('%d %b %Y  \u00b7  %I:%M %p')
    ft = Table([[
        _p("MASTAN CATERING &amp; SERVICES", size=8, bold=True,
           color=colors.HexColor('#aaa')),
        _p(f'Generated: {gen_str}', size=8, color=colors.HexColor('#bbb'), align=2),
    ]], colWidths=[FIN_W * 0.5, FIN_W * 0.5])
    ft.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    el.append(ft)

    doc.build(el)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
