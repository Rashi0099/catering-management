from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin-panel/login/')(view_func)
from django.http import JsonResponse, HttpResponse
import csv
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from bookings.models import Booking, BookingPayment, EventApplication
from menu.models import MenuItem, MenuCategory
from gallery.models import GalleryImage
from staff.models import Staff, StaffPayout, StaffApplication


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')
    if request.method == 'POST':
        staff_id = request.POST.get('username', '').strip().upper()
        password = request.POST.get('password', '')
        user = authenticate(request, username=staff_id, password=password)
        if user and user.is_staff:
            login(request, user)
            return redirect('admin_dashboard')
        messages.error(request, 'Invalid credentials or insufficient permissions.')
    return render(request, 'admin/login.html')


def admin_logout(request):
    logout(request)
    return redirect('admin_login')


@admin_required
def dashboard(request):
    today = timezone.now().date()
    this_week = today + timedelta(days=7)

    total_bookings     = Booking.objects.count()
    pending_bookings   = Booking.objects.filter(status='pending').count()
    confirmed_bookings = Booking.objects.filter(status='confirmed').count()
    upcoming_events    = Booking.objects.filter(event_date__gte=today, event_date__lte=this_week).count()

    total_revenue   = Booking.objects.filter(status__in=['confirmed','completed']).aggregate(t=Sum('quoted_price'))['t'] or 0
    total_received  = Booking.objects.aggregate(t=Sum('amount_received'))['t'] or 0
    pending_payment = total_revenue - total_received

    recent_bookings = Booking.objects.select_related('created_by').order_by('-created_at')[:5]
    upcoming        = Booking.objects.select_related('created_by').filter(event_date__gte=today, status__in=['confirmed','pending']).order_by('event_date')[:5]
    event_counts    = list(Booking.objects.values('event_type').annotate(count=Count('event_type')))

    context = {
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'confirmed_bookings': confirmed_bookings,
        'upcoming_events': upcoming_events,
        'total_revenue': total_revenue,
        'total_received': total_received,
        'pending_payment': pending_payment,
        'recent_bookings': recent_bookings,
        'upcoming': upcoming,
        'event_counts': event_counts,
        'menu_count': MenuItem.objects.count(),
        'staff_count': Staff.objects.filter(is_active=True).count(),
        'page': 'dashboard',
        'pending_count': pending_bookings,
    }
    return render(request, 'admin/dashboard.html', context)


@admin_required
def bookings_list(request):
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment', '')
    search = request.GET.get('search', '')
    bookings = Booking.objects.select_related('created_by').all()

    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if payment_filter:
        bookings = bookings.filter(payment_status=payment_filter)
    if search:
        bookings = bookings.filter(Q(name__icontains=search) | Q(phone__icontains=search))

    bookings = bookings.order_by('-created_at')
    paginator = Paginator(bookings, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {'bookings': page_obj, 'status_filter': status_filter,
               'payment_filter': payment_filter, 'search': search, 'page': 'bookings',
               'pending_count': Booking.objects.filter(status='pending').count()}
    return render(request, 'admin/bookings.html', context)


@admin_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    all_staff = Staff.objects.filter(is_active=True)
    payments = booking.payments.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_booking':
            old_status = booking.status
            booking.status       = request.POST.get('status', booking.status)
            booking.admin_notes  = request.POST.get('admin_notes', '')
            booking.quoted_price = request.POST.get('quoted_price') or None
            booking.save()
            # Assign staff
            staff_ids = request.POST.getlist('assigned_to')
            booking.assigned_to.set(staff_ids)
            
            # Event completion tracking
            if old_status != 'completed' and booking.status == 'completed':
                for staff_id in staff_ids:
                    s = Staff.objects.get(id=staff_id)
                    s.total_events_completed += 1
                    s.save()
                    if s.level == 'C' and s.total_events_completed >= 20:
                        from staff.models import PromotionRequest
                        if not PromotionRequest.objects.filter(staff=s, status='pending').exists():
                            PromotionRequest.objects.create(
                                staff=s,
                                current_level='C',
                                requested_level='B'
                            )
            
            # Sync EventApplication statuses based on manual assignment changes
            from bookings.models import EventApplication
            # If manually added to event, mark any pending app as approved
            EventApplication.objects.filter(booking=booking, staff_id__in=staff_ids, status='pending').update(status='approved')
            # If manually removed from event, mark any cancel_request as cancelled
            EventApplication.objects.filter(booking=booking, status='cancel_requested').exclude(staff_id__in=staff_ids).update(status='cancelled')
            
            messages.success(request, 'Booking updated!')
        elif action == 'add_payment':
            BookingPayment.objects.create(
                booking     = booking,
                amount      = request.POST['amount'],
                method      = request.POST['method'],
                reference   = request.POST.get('reference', ''),
                received_on = request.POST['received_on'],
                received_by = request.user,
                notes       = request.POST.get('notes', ''),
            )
            messages.success(request, f'Payment of Rs.{request.POST["amount"]} recorded!')
        
        elif action == 'mark_attendance':
            from staff.models import StaffAttendance
            staff_ids = request.POST.getlist('attendance_staff_id')
            for sid in staff_ids:
                status = request.POST.get(f'attendance_status_{sid}', 'present')
                r_time = request.POST.get(f'reaching_time_{sid}') or None
                notes  = request.POST.get(f'attendance_notes_{sid}', '')
                
                att, created = StaffAttendance.objects.get_or_create(
                    booking=booking,
                    staff_id=sid,
                    date=booking.event_date,
                    defaults={'status': status, 'reaching_time': r_time, 'notes': notes}
                )
                if not created:
                    att.status = status
                    att.reaching_time = r_time
                    att.notes = notes
                    att.save()
            messages.success(request, 'Attendance and reaching times saved successfully!')

        return redirect('admin_booking_detail', pk=pk)

    pending_applications = booking.applications.filter(status='pending')
    cancel_requests = booking.applications.filter(status='cancel_requested')

    grouped_staff = {}
    for staff in all_staff:
        level = staff.get_level_display()
        if level not in grouped_staff:
            grouped_staff[level] = []
        grouped_staff[level].append(staff)

    # Sort dictionary by level name
    grouped_staff = dict(sorted(grouped_staff.items()))

    attendances = booking.staff_attendance.filter(date=booking.event_date)
    attendance_map = {att.staff_id: att for att in attendances}
    
    assigned_staff_with_att = []
    for s in booking.assigned_to.all():
        assigned_staff_with_att.append({
            'staff': s,
            'attendance': attendance_map.get(s.pk)
        })

    context = {
        'booking': booking,
        'all_staff': all_staff,
        'grouped_staff': grouped_staff,
        'attendance_map': attendance_map,
        'assigned_staff_with_att': assigned_staff_with_att,
        'payments': payments,
        'pending_applications': pending_applications,
        'cancel_requests': cancel_requests,
        'today': timezone.now().date(),
        'page': 'bookings',
        'pending_count': Booking.objects.filter(status='pending').count(),
    }
    return render(request, 'admin/booking_detail.html', context)


@admin_required
def download_attendance(request, pk):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    booking = get_object_or_404(Booking, pk=pk)
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


@admin_required
def handle_application(request, pk, app_id, action):
    application = get_object_or_404(EventApplication, pk=app_id, booking_id=pk)
    if action == 'approve_app':
        application.status = 'approved'
        application.save()
        application.booking.assigned_to.add(application.staff)
        messages.success(request, f'{application.staff.full_name} approved and assigned to event.')
    elif action == 'reject_app':
        application.status = 'rejected'
        application.save()
        messages.success(request, 'Application rejected.')
    elif action == 'approve_cancel':
        application.status = 'cancelled'
        application.save()
        application.booking.assigned_to.remove(application.staff)
        messages.success(request, f'Cancel request approved. {application.staff.full_name} removed from event.')
    elif action == 'reject_cancel':
        application.status = 'approved' # Revert to approved since cancel is denied
        application.save()
        messages.success(request, 'Cancel request rejected.')
    return redirect('admin_booking_detail', pk=pk)



@admin_required
def admin_create_booking(request):
    if request.method == 'POST':
        try:
            booking = Booking.objects.create(
                name        = request.POST['name'],
                email       = request.POST.get('email', ''),
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
                status               = 'confirmed', # Manual admin entry defaults to confirmed
                quoted_price         = request.POST.get('budget') or None
            )
            # Admin creating booking is not necessarily assigning themselves, but we can assign later
            messages.success(request, f'Booking for {booking.name} created successfully!')
            return redirect('admin_booking_detail', pk=booking.pk)
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
            
    return render(request, 'admin/create_booking.html', {
        'page': 'bookings',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })


@admin_required
def update_booking_status(request, pk):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(Booking.STATUS_CHOICES):
            old_status = booking.status
            booking.status = new_status
            booking.save()
            if old_status != 'completed' and new_status == 'completed':
                for s in booking.assigned_to.all():
                    s.total_events_completed += 1
                    s.save()
                    if s.level == 'C' and s.total_events_completed >= 20:
                        from staff.models import PromotionRequest
                        if not PromotionRequest.objects.filter(staff=s, status='pending').exists():
                            PromotionRequest.objects.create(
                                staff=s,
                                current_level='C',
                                requested_level='B'
                            )
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ── Staff Management (ADMIN) ─────────────────────────────────────────────────

@admin_required
def staff_requests(request):
    pending_apps = EventApplication.objects.filter(status='pending').select_related('staff', 'booking').order_by('-created_at')
    cancel_reqs = EventApplication.objects.filter(status='cancel_requested').select_related('staff', 'booking').order_by('-created_at')
    
    context = {
        'pending_apps': pending_apps,
        'cancel_reqs': cancel_reqs,
        'page': 'staff_requests',
        'pending_count': Booking.objects.filter(status='pending').count(),
    }
    return render(request, 'admin/staff_requests.html', context)


@admin_required
def staff_applications(request):
    applications = StaffApplication.objects.filter(status='pending').order_by('-created_at')
    context = {
        'applications': applications,
        'page': 'staff_applications',
        'pending_count': Booking.objects.filter(status='pending').count(),
    }
    return render(request, 'admin/staff_applications.html', context)

@admin_required
def handle_staff_application(request, pk, action):
    application = get_object_or_404(StaffApplication, pk=pk)
    if action == 'approve':
        try:
            from staff.models import generate_staff_id
            new_id = generate_staff_id()
            
            # Create Staff user with default password
            Staff.objects.create_user(
                staff_id=new_id,
                password='password123',
                full_name=application.full_name,
                level='C',
                phone=application.phone_1,
                phone_2=application.phone_2,
                email=application.email,
                age=application.age,
                height=application.height,
                blood_group=application.blood_group,
                guardian_name=application.guardian_name,
                guardian_phone=application.guardian_phone,
                main_locality=application.main_locality,
                place=application.place,
                education=application.education,
                aadhar_card_no=application.aadhar_card_no
            )
            
            application.status = 'approved'
            application.save()
            messages.success(request, f'Staff created! ID: {new_id} | Password: password123')
        except Exception as e:
            messages.error(request, f'Error creating staff: {str(e)}')
    elif action == 'reject':
        application.status = 'rejected'
        application.save()
        messages.success(request, 'Application rejected.')
        
    return redirect('admin_staff_applications')

@admin_required
def staff_list(request):
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')

    from django.db.models import Count, Q
    
    booking_filter = Q()
    if month: booking_filter &= Q(bookings__event_date__month=month)
    if year: booking_filter &= Q(bookings__event_date__year=year)

    staff = Staff.objects.filter(is_active=True).annotate(
        filtered_booking_count=Count('bookings', filter=booking_filter, distinct=True)
    )

    if month or year:
        # If the user explicitly filtered by month or year, only show staff who worked in that period natively.
        staff = staff.filter(filtered_booking_count__gt=0)
        
    staff = staff.order_by('full_name')

    q = request.GET.get('q', '').strip()
    level = request.GET.get('level', '')
    locality = request.GET.get('locality', '')

    from django.db.models import Q
    if q:
        staff = staff.filter(
            Q(full_name__icontains=q) |
            Q(staff_id__icontains=q) |
            Q(phone__icontains=q)
        )
    if level:
        staff = staff.filter(level=level)
    if locality:
        staff = staff.filter(main_locality=locality)
    
    sort = request.GET.get('sort', '')
    if sort == 'booking_count_desc':
        staff = staff.order_by('-filtered_booking_count', 'full_name')
    elif sort == 'booking_count_asc':
        staff = staff.order_by('filtered_booking_count', 'full_name')
    else:
        staff = staff.order_by('full_name')

    paginator = Paginator(staff, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    context = {
        'staff': page_obj,
        'page': 'staff',
        'pending_count': Booking.objects.filter(status='pending').count(),
    }
    return render(request, 'admin/staff_list.html', context)


@admin_required
def staff_add(request):
    if request.method == 'POST':
        full_name = request.POST['full_name']
        level = request.POST['level']
        daily_rate = request.POST.get('daily_rate', 0)
        phone = request.POST.get('phone', '')
        phone_2 = request.POST.get('phone_2', '')
        email = request.POST.get('email', '')
        age = request.POST.get('age') or None
        height = request.POST.get('height', '')
        blood_group = request.POST.get('blood_group', '')
        guardian_name = request.POST.get('guardian_name', '')
        guardian_phone = request.POST.get('guardian_phone', '')
        main_locality = request.POST.get('main_locality', '')
        place = request.POST.get('place', '')
        education = request.POST.get('education', '')
        aadhar_card_no = request.POST.get('aadhar', '')

        try:
            from staff.models import generate_staff_id
            new_id = generate_staff_id()
            
            member = Staff.objects.create_user(
                staff_id=new_id,
                password='password123',
                full_name=full_name,
                level=level,
                daily_rate=daily_rate,
                phone=phone,
                phone_2=phone_2,
                email=email,
                age=age,
                height=height,
                blood_group=blood_group,
                guardian_name=guardian_name,
                guardian_phone=guardian_phone,
                main_locality=main_locality,
                place=place,
                education=education,
                aadhar_card_no=aadhar_card_no
            )
            messages.success(request, f'Staff added! Default password is "password123". ID: {member.staff_id}')
            return redirect('admin_staff')
        except Exception as e:
            messages.error(request, f'Error adding staff: {str(e)}')
            return redirect('admin_staff_add')

    return render(request, 'admin/staff_add.html', {
        'page': 'staff',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })


@admin_required
def staff_edit(request, pk):
    member = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        member.full_name = request.POST['full_name']
        member.level = request.POST['level']
        member.daily_rate = request.POST.get('daily_rate', 0)
        member.phone = request.POST.get('phone', '')
        member.phone_2 = request.POST.get('phone_2', '')
        member.email = request.POST.get('email', '')
        member.age = request.POST.get('age') or None
        member.height = request.POST.get('height', '')
        member.blood_group = request.POST.get('blood_group', '')
        member.guardian_name = request.POST.get('guardian_name', '')
        member.guardian_phone = request.POST.get('guardian_phone', '')
        member.main_locality = request.POST.get('main_locality', '')
        member.place = request.POST.get('place', '')
        member.education = request.POST.get('education', '')
        member.aadhar_card_no = request.POST.get('aadhar', '')
        member.is_active = request.POST.get('is_active') == 'on'
        member.save()
        messages.success(request, f'Staff {member.full_name} updated successfully!')
        return redirect('admin_staff_detail', pk=member.pk)

    return render(request, 'admin/staff_edit.html', {
        'member': member,
        'page': 'staff',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })



@admin_required
def staff_detail(request, pk):
    member = get_object_or_404(Staff, pk=pk)
    today  = timezone.now().date()

    bookings   = member.bookings.all().order_by('-event_date')
    payouts    = member.payouts.order_by('-created_at')
    revenue    = member.total_revenue_generated()
    total_paid = member.total_paid_out()
    pending    = member.pending_payout()

    if request.method == 'POST' and request.POST.get('action') == 'add_payout':
        StaffPayout.objects.create(
            staff       = member,
            payout_type = request.POST['payout_type'],
            amount      = request.POST['amount'],
            description = request.POST.get('description', ''),
            status      = request.POST.get('status', 'pending'),
            paid_on     = request.POST.get('paid_on') or None,
            paid_by     = request.user.full_name,
            reference   = request.POST.get('reference', ''),
            booking_id  = request.POST.get('booking_id') or None,
        )
        messages.success(request, 'Payout recorded!')
        return redirect('admin_staff_detail', pk=pk)

    context = {
        'member': member,
        'bookings': bookings[:10],
        'payouts': payouts,
        'revenue': revenue,
        'total_paid': total_paid,
        'pending': pending,
        'today': today,
        'page': 'staff',
        'pending_count': Booking.objects.filter(status='pending').count(),
        'all_bookings': member.bookings.all(),
    }
    return render(request, 'admin/staff_detail.html', context)


@admin_required
def mark_payout_paid(request, pk):
    payout = get_object_or_404(StaffPayout, pk=pk)
    payout.status  = 'paid'
    payout.paid_on = timezone.now().date()
    payout.paid_by = request.user.full_name
    payout.save()
    messages.success(request, f'Payout of Rs.{payout.amount} marked as paid!')
    return redirect('admin_staff_detail', pk=payout.staff.pk)


# ── Menu ──────────────────────────────────────────────────────────────────────

@admin_required
def menu_list(request):
    categories = MenuCategory.objects.prefetch_related('items').all()
    context = {'categories': categories, 'page': 'menu',
               'pending_count': Booking.objects.filter(status='pending').count()}
    return render(request, 'admin/menu.html', context)


@admin_required
def menu_add(request):
    if request.method == 'POST':
        MenuItem.objects.create(
            category_id   = request.POST['category'],
            name          = request.POST['name'],
            description   = request.POST['description'],
            price         = request.POST['price'],
            is_vegetarian = request.POST.get('is_vegetarian') == 'on',
            is_featured   = request.POST.get('is_featured') == 'on',
        )
        messages.success(request, 'Menu item added!')
        return redirect('admin_menu')
    categories = MenuCategory.objects.all()
    return render(request, 'admin/menu_add.html', {
        'categories': categories, 'page': 'menu',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })


@admin_required
def menu_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    item.delete()
    messages.success(request, f'"{item.name}" removed.')
    return redirect('admin_menu')


@admin_required
def gallery_list(request):
    images = GalleryImage.objects.order_by('-uploaded_at')
    context = {'images': images, 'page': 'gallery',
               'pending_count': Booking.objects.filter(status='pending').count()}
    return render(request, 'admin/gallery.html', context)


@admin_required
def team_page(request):
    staff = Staff.objects.filter(is_active=True)
    return render(request, 'admin/team.html', {
        'staff': staff, 'page': 'team',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })


@admin_required
def staff_promotions(request):
    from staff.models import PromotionRequest
    requests = PromotionRequest.objects.filter(status='pending').order_by('-created_at')
    return render(request, 'admin/staff_promotions.html', {
        'requests': requests,
        'page': 'staff_promotions',
        'pending_count': Booking.objects.filter(status='pending').count(),
    })


@admin_required
def handle_promotion(request, pk, action):
    from staff.models import PromotionRequest
    promotion = get_object_or_404(PromotionRequest, pk=pk)
    if action == 'approve':
        promotion.status = 'approved'
        promotion.staff.level = promotion.requested_level
        promotion.staff.save()
        promotion.save()
        messages.success(request, f'Promotion approved! {promotion.staff.full_name} is now {promotion.requested_level} Level.')
    elif action == 'reject':
        promotion.status = 'rejected'
        promotion.save()
        messages.success(request, 'Promotion rejected.')
    return redirect('admin_staff_promotions')
