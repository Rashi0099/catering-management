from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.db.models import Sum, Count, Q

from .models import Staff, StaffPayout, StaffAttendance
from bookings.models import Booking, BookingPayment


# ── Authentication ───────────────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_change_password(request):
    """Handles password change for authenticated staff members."""
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.forms import PasswordChangeForm
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Prevents logout after change
            messages.success(request, 'Your password was successfully updated!')
            return redirect('staff_dashboard')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'staff/password_change.html', {'form': form})

def staff_login(request):
    """Authenticates and logs in a staff member using their staff ID."""
    if request.user.is_authenticated:
        return redirect('staff_dashboard')
    if request.method == 'POST':
        staff_id = request.POST.get('staff_id', '').strip().upper()
        password = request.POST.get('password', '')
        user = authenticate(request, username=staff_id, password=password)
        if user and user.is_active:
            login(request, user)
            return redirect('staff_dashboard')
        messages.error(request, 'Invalid Staff ID or password.')
    return render(request, 'staff/login.html')


def staff_logout(request):
    """Logs out the current staff member and redirects to login."""
    logout(request)
    return redirect('staff_login')


@login_required(login_url='/staff/login/')
def staff_download_attendance(request, pk):
    """Generates and downloads a PDF report of staff attendance for a specific booking."""
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    me = request.user
    if me.level != 'captain':
        messages.error(request, 'Only Captains can download PDF reports.')
        return redirect('staff_booking_detail', pk=pk)

    booking = get_object_or_404(Booking, pk=pk)
    
    # Check access
    is_assigned = booking.assigned_to.filter(id=me.id).exists()
    if not is_assigned and not me.is_staff:
        messages.error(request, 'You do not have access to this booking.')
        return redirect('staff_bookings')

    attendances = booking.staff_attendance.filter(date=booking.event_date).select_related('staff')
    assigned_staff = booking.assigned_to.all()
    attendance_map = {att.staff_id: att for att in attendances}
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=14,
        textColor=colors.HexColor('#1a1a1a')
    )
    subtitle_style = ParagraphStyle(
        name='SubTitleStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=20,
        textColor=colors.HexColor('#666666')
    )
    
    elements.append(Paragraph(f"Event Attendance Report - Booking #{booking.pk}", title_style))
    
    client_info = f"<b>Client:</b> {booking.name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {booking.event_date.strftime('%d %b %Y')} <br/>"
    client_info += f"<b>Event Type:</b> {booking.get_event_type_display()} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Venue:</b> {booking.venue or 'N/A'}"
    elements.append(Paragraph(client_info, subtitle_style))
    elements.append(Spacer(1, 10))
    
    data = [['Staff ID', 'Name', 'Role', 'Reaching Time', 'Status', 'Wage (Rs)']]
    total_wage = 0
    
    for staff in assigned_staff:
        att = attendance_map.get(staff.pk)
        raw_status = att.status if att else 'absent'
        status = att.get_status_display() if att else 'Not Marked'
        r_time = att.reaching_time.strftime('%I:%M %p') if att and att.reaching_time else '—'
        wage = staff.daily_rate
        if raw_status in ['present', 'half_day']:
            total_wage += wage
            
        data.append([
            staff.staff_id,
            staff.full_name,
            staff.get_level_display(),
            r_time,
            status,
            f"Rs.{wage}"
        ])
        
    data.append(['', '', '', '', 'Total Estimated Wages:', f"Rs.{total_wage}"])
    
    table = Table(data, colWidths=[70, 140, 100, 80, 70, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f4f4f4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, -1), (-2, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f4f4f4')),
        ('GRID', (0, 0), (-1, -2), 1, colors.HexColor('#dddddd')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#dddddd')),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#dddddd')),
    ]))
    
    elements.append(table)
    
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        name='FooterStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#999999'),
        alignment=2 # Right align
    )
    elements.append(Paragraph(f"Generated on {timezone.now().strftime('%d %b %Y, %I:%M %p')}", footer_style))
    
    doc.build(elements)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="attendance_booking_{booking.pk}.pdf"'
    return response


# ── Staff Dashboard ──────────────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_dashboard(request):
    """Renders the main dashboard showing personal data, upcoming bookings, and payout summaries."""
    me = request.user
    today = timezone.now().date()

    my_bookings   = me.bookings.all()
    my_created    = me.bookings_created.all()
    pending       = my_bookings.filter(status='pending')
    upcoming      = my_bookings.filter(event_date__gte=today, status='confirmed').order_by('event_date')[:5]
    available_bookings = Booking.objects.filter(status='confirmed', event_date__gte=today).exclude(assigned_to=me).order_by('event_date')[:5]
    recent        = my_created.order_by('-created_at')[:5]
    my_revenue    = my_bookings.filter(status__in=['confirmed','completed']).aggregate(t=Sum('quoted_price'))['t'] or 0
    my_payouts    = me.payouts.order_by('-created_at')[:5]
    total_earned  = me.payouts.filter(status='paid').aggregate(t=Sum('amount'))['t'] or 0
    pending_pay   = me.payouts.filter(status='pending').aggregate(t=Sum('amount'))['t'] or 0

    my_applications = me.event_applications.all()
    pending_app_booking_ids = list(my_applications.filter(status='pending').values_list('booking_id', flat=True))
    cancel_req_booking_ids = list(my_applications.filter(status='cancel_requested').values_list('booking_id', flat=True))

    remaining_events = max(0, 20 - me.total_events_completed) if me.level == 'C' else None
    latest_promotion = me.promotion_requests.order_by('-created_at').first()

    return render(request, 'staff/dashboard.html', {
        'me': me,
        'total_bookings': my_bookings.count(),
        'confirmed_count': my_bookings.filter(status='confirmed').count(),
        'completed_count': my_bookings.filter(status='completed').count(),
        'pending_count':   pending.count(),
        'upcoming': upcoming,
        'available_bookings': available_bookings,
        'recent_bookings': recent,
        'my_revenue': my_revenue,
        'my_payouts': my_payouts,
        'total_earned': total_earned,
        'pending_pay': pending_pay,
        'pending_app_booking_ids': pending_app_booking_ids,
        'cancel_req_booking_ids': cancel_req_booking_ids,
        'remaining_events': remaining_events,
        'latest_promotion': latest_promotion,
    })


# ── Staff Booking Management ─────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_bookings(request):
    """Displays a paginated list of bookings either created by or assigned to the staff."""
    me = request.user
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')

    # Staff see bookings they created OR are assigned to
    bookings = Booking.objects.filter(
        Q(created_by=me) | Q(assigned_to=me)
    ).distinct()

    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if search:
        bookings = bookings.filter(
            Q(name__icontains=search) | Q(phone__icontains=search)
        )

    bookings = bookings.select_related('created_by').order_by('event_date')
    paginator = Paginator(bookings, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'staff/bookings.html', {
        'bookings': page_obj,
        'status_filter': status_filter,
        'search': search,
    })


@login_required(login_url='/staff/login/')
def staff_create_booking(request):
    """Allows staff to create a new client booking and assigns them as the creator."""
    me = request.user
    if request.method == 'POST':
        try:
            booking = Booking.objects.create(
                name        = request.POST['name'],
                email       = request.POST['email'],
                phone       = request.POST['phone'],
                company     = request.POST.get('company', ''),
                event_type  = request.POST['event_type'],
                event_date  = request.POST['event_date'],
                event_time  = request.POST.get('event_time') or None,
                venue       = request.POST.get('venue', ''),
                guest_count = int(request.POST.get('guest_count', 1)),
                budget      = request.POST.get('budget') or None,
                dietary_requirements = request.POST.get('dietary_requirements', ''),
                special_requests     = request.POST.get('special_requests', ''),
                message              = request.POST.get('message', ''),
                created_by  = me,
            )
            booking.assigned_to.add(me)
            messages.success(request, f'Booking for {booking.name} created successfully!')
            return redirect('staff_booking_detail', pk=booking.pk)
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')

    return render(request, 'staff/create_booking.html')


@login_required(login_url='/staff/login/')
def staff_booking_detail(request, pk):
    """Shows full details of a booking and processes new payments and attendance marking."""
    me = request.user
    # Staff can only view their own bookings
    booking = get_object_or_404(
        Booking,
        pk=pk
    )
    # Check access
    is_assigned = booking.assigned_to.filter(id=me.id).exists()
    if booking.created_by != me and not is_assigned and not me.is_staff:
        messages.error(request, 'You do not have access to this booking.')
        return redirect('staff_bookings')

    payments = booking.payments.all()

    if request.method == 'POST' and request.POST.get('action') == 'add_payment':
        try:
            BookingPayment.objects.create(
                booking     = booking,
                amount      = request.POST['amount'],
                method      = request.POST['method'],
                reference   = request.POST.get('reference', ''),
                received_on = request.POST['received_on'],
                received_by = me,
                notes       = request.POST.get('notes', ''),
            )
            messages.success(request, f'Payment of ₹{request.POST["amount"]} recorded!')
            return redirect('staff_booking_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'Error recording payment: {e}')

    if request.method == 'POST' and request.POST.get('action') == 'mark_attendance':
        if me.level != 'captain' and not me.is_staff:
            messages.error(request, 'Only Captains can mark attendance.')
            return redirect('staff_booking_detail', pk=pk)
            
        staff_ids = request.POST.getlist('staff_ids[]')
        date_str = request.POST.get('attendance_date', booking.event_date.strftime('%Y-%m-%d'))
        
        for sid in staff_ids:
            status = request.POST.get(f'status_{sid}')
            reaching_time_str = request.POST.get(f'reaching_{sid}')
            notes = request.POST.get(f'notes_{sid}', '')
            
            try:
                staff_member = Staff.objects.get(id=sid)
            except Staff.DoesNotExist:
                continue
            
            reaching_time = None
            if reaching_time_str:
                try:
                    reaching_time = datetime.strptime(reaching_time_str, '%H:%M').time()
                except ValueError:
                    pass
            
            StaffAttendance.objects.update_or_create(
                staff=staff_member,
                date=date_str,
                booking=booking,
                defaults={
                    'status': status,
                    'reaching_time': reaching_time,
                    'notes': notes
                }
            )
        messages.success(request, f'Attendance marked for {len(staff_ids)} staff members.')
        return redirect('staff_booking_detail', pk=pk)

    assigned_staff_list = []
    attendances = StaffAttendance.objects.filter(booking=booking, date=booking.event_date)
    att_map = {a.staff_id: a for a in attendances}
    
    for s in booking.assigned_to.all():
        assigned_staff_list.append({
            'staff': s,
            'attendance': att_map.get(s.id)
        })

    return render(request, 'staff/booking_detail.html', {
        'me': me,
        'booking': booking,
        'payments': payments,
        'today': timezone.now().date(),
        'assigned_staff_list': assigned_staff_list,
    })


@login_required(login_url='/staff/login/')
def staff_apply_booking(request, pk):
    """Handles staff applications to work on available, confirmed upcoming bookings."""
    booking = get_object_or_404(Booking, pk=pk, status='confirmed')
    # If GET, render a simple apply form
    if request.method == 'GET':
        return render(request, 'staff/apply_booking.html', {'booking': booking})
    
    # If POST, process the application
    if request.method == 'POST':
        applicant_name = request.POST.get('applicant_name', request.user.full_name)
        applicant_phone = request.POST.get('applicant_phone', request.user.phone)
        
        # Check if they already applied or are assigned
        from bookings.models import EventApplication
        if EventApplication.objects.filter(booking=booking, staff=request.user).exists():
            messages.info(request, "You have already applied for this event.")
        elif request.user in booking.assigned_to.all():
            messages.info(request, "You are already assigned to this event.")
        else:
            EventApplication.objects.create(
                booking=booking,
                staff=request.user,
                applicant_name=applicant_name,
                applicant_phone=applicant_phone,
                status='pending'
            )
            messages.success(request, f'Application submitted for {booking.name}!')
        return redirect('staff_dashboard')


@login_required(login_url='/staff/login/')
def staff_cancel_request(request, pk):
    """Files a cancellation request when a staff member wants to back out of an assigned event."""
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        if request.user in booking.assigned_to.all():
            from bookings.models import EventApplication
            application = booking.applications.filter(staff=request.user).first()
            if application:
                application.status = 'cancel_requested'
                application.save()
            else:
                # Provide a way to ask for cancel even if they were assigned without applying manually
                EventApplication.objects.create(
                    booking=booking,
                    staff=request.user,
                    applicant_name=request.user.full_name,
                    applicant_phone=request.user.phone,
                    status='cancel_requested'
                )
            messages.success(request, "Cancel request sent to admin for approval.")
        else:
            messages.error(request, "You are not assigned to this event.")
    return redirect('staff_dashboard')


# ── Staff Payouts (view own payouts) ─────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_payouts(request):
    """Displays the payout history and pending payout balances for the logged-in staff member."""
    me = request.user
    payouts = me.payouts.select_related('booking').order_by('-created_at')
    
    paginator = Paginator(payouts, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    total_earned = payouts.filter(status='paid').aggregate(t=Sum('amount'))['t'] or 0
    pending_amt  = payouts.filter(status='pending').aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'staff/payouts.html', {
        'payouts': page_obj,
        'total_earned': total_earned,
        'pending_amt': pending_amt,
    })
