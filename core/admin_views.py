from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin-panel/login/')(view_func)
from django.http import JsonResponse, HttpResponse
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
        if user and user.is_staff and user.is_active:
            login(request, user)
            # Optional: Force password change logic for admins too if needed
            if getattr(user, 'must_change_password', False):
                messages.warning(request, '⚠️ You must change your default password.')
                return redirect('staff_change_password')
            return redirect('admin_dashboard')
        messages.error(request, 'Invalid credentials or insufficient permissions.')
    return render(request, 'admin/login.html')


def admin_logout(request):
    if request.method == 'POST':
        logout(request)
    return redirect('admin_login')


from django.core.cache import cache

from core.utils import auto_complete_past_bookings, get_pending_count

@admin_required
def dashboard(request):
    # Auto-complete past events
    auto_complete_past_bookings()
    
    today = timezone.now().date()
    this_week = today + timedelta(days=7)

    cache_key = 'admin_dashboard_stats'
    cached_stats = cache.get(cache_key)

    if not cached_stats:
        total_bookings     = Booking.objects.count()
        pending_bookings   = Booking.objects.filter(status='pending').count()
        confirmed_bookings = Booking.objects.filter(status='confirmed').count()
        upcoming_events    = Booking.objects.filter(event_date__gte=today, event_date__lte=this_week).count()

        total_revenue   = Booking.objects.filter(status__in=['confirmed','completed']).aggregate(t=Sum('quoted_price'))['t'] or 0
        total_received  = Booking.objects.aggregate(t=Sum('amount_received'))['t'] or 0
        pending_payment = total_revenue - total_received
        event_counts    = list(Booking.objects.values('event_type').annotate(count=Count('event_type')))
        
        cached_stats = {
            'total_bookings': total_bookings,
            'pending_bookings': pending_bookings,
            'confirmed_bookings': confirmed_bookings,
            'upcoming_events': upcoming_events,
            'total_revenue': total_revenue,
            'total_received': total_received,
            'pending_payment': pending_payment,
            'event_counts': event_counts,
            'menu_count': MenuItem.objects.count(),
            'staff_count': Staff.objects.filter(is_active=True).count(),
        }
        cache.set(cache_key, cached_stats, 60 * 5) # 5 minutes

    # These are dynamic/changing elements so we shouldn't cache them heavily
    recent_bookings = Booking.objects.select_related('created_by').order_by('-created_at')[:5]
    upcoming        = Booking.objects.select_related('created_by').filter(event_date__gte=today, status__in=['confirmed','pending']).order_by('event_date')[:5]

    context = {
        **cached_stats,
        'recent_bookings': recent_bookings,
        'upcoming': upcoming,
        'page': 'dashboard',
        'pending_count': cached_stats.get('pending_bookings', 0),
    }
    return render(request, 'admin/dashboard.html', context)


@admin_required
def bookings_list(request):
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment', '')
    search = request.GET.get('search', '')
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', '')
    type_filter = request.GET.get('type', '')
    session_filter = request.GET.get('session', '')
    
    bookings = Booking.objects.select_related('created_by').all()

    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if payment_filter:
        bookings = bookings.filter(payment_status=payment_filter)
    if month_filter:
        bookings = bookings.filter(event_date__month=month_filter)
    if year_filter:
        bookings = bookings.filter(event_date__year=year_filter)
    if type_filter:
        bookings = bookings.filter(event_type=type_filter)
    if session_filter:
        bookings = bookings.filter(session=session_filter)
        
    if search:
        bookings = bookings.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(venue__icontains=search) |
            Q(location_name__icontains=search) |
            Q(event_type__icontains=search)
        )

    bookings = bookings.order_by('-created_at')
    paginator = Paginator(bookings, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {'bookings': page_obj, 'status_filter': status_filter,
               'payment_filter': payment_filter, 'search': search, 
               'month_filter': month_filter, 'year_filter': year_filter,
               'type_filter': type_filter, 'session_filter': session_filter,
               'page': 'bookings'}
    return render(request, 'admin/bookings.html', context)


@admin_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    booking.generate_default_tasks()
    all_staff = Staff.objects.filter(is_active=True)
    payments = booking.payments.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_booking':
            old_status = booking.status
            old_quoted_price = booking.quoted_price
            booking.status       = request.POST.get('status', booking.status)
            booking.admin_notes  = request.POST.get('admin_notes', '')
            booking.quoted_price = request.POST.get('quoted_price') or None
            booking.save()
            
            # Fix 3: If quoted_price changed, recalculate payment totals immediately
            if booking.quoted_price != old_quoted_price:
                BookingPayment._recalc_booking_totals_for(booking)
            # Assign staff
            staff_ids = request.POST.getlist('assigned_to')
            booking.assigned_to.set(staff_ids)
            
            # Event completion tracking
            if old_status != 'completed' and booking.status == 'completed':
                for staff_id in staff_ids:
                    s = Staff.objects.get(id=staff_id)
                    # Use .count() to stay in sync — never += 1 which can drift
                    s.total_events_completed = s.bookings.filter(status='completed').count()
                    s.save(update_fields=['total_events_completed'])
                    if s.level == 'C':
                        day_count = s.bookings.filter(status='completed', session='day').count()
                        night_count = s.bookings.filter(status='completed', session='night').count()
                        long_work_count = s.bookings.filter(status='completed', is_long_work=True).count()
                        if day_count >= 10 and night_count >= 5 and long_work_count >= 5:
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
                on_time = request.POST.get(f'on_time_{sid}') == 'on'
                shoes = request.POST.get(f'shoes_{sid}') == 'on'
                uniform = request.POST.get(f'uniform_{sid}') == 'on'
                grooming = request.POST.get(f'grooming_{sid}') == 'on'
                payment_given = request.POST.get(f'payment_given_{sid}') == 'on'
                
                att, created = StaffAttendance.objects.get_or_create(
                    booking=booking,
                    staff_id=sid,
                    date=booking.event_date,
                    defaults={'status': status, 'reaching_time': r_time, 'on_time': on_time, 'shoes': shoes, 'uniform': uniform, 'grooming': grooming, 'payment_given': payment_given}
                )
                if not created:
                    att.status = status
                    att.reaching_time = r_time
                    att.on_time = on_time
                    att.shoes = shoes
                    att.uniform = uniform
                    att.grooming = grooming
                    att.payment_given = payment_given
                    att.save()
            messages.success(request, 'Attendance and fines saved successfully!')

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
    applications_map = {app.staff_id: app for app in booking.applications.filter(status__in=['approved', 'pending'])}
    
    assigned_staff_with_att = []
    coat_counts = {'S': 0, 'M': 0, 'L': 0, 'XL': 0, 'XXL': 0}
    filled_counts = {'captain': 0, 'A': 0, 'B': 0, 'C': 0}

    for s in booking.assigned_to.all():
        if s.coat_size and s.coat_size in coat_counts:
            coat_counts[s.coat_size] += 1
        
        # Calculate filled counts by level
        if s.level == 'captain': filled_counts['captain'] += 1
        elif s.level == 'A': filled_counts['A'] += 1
        elif s.level == 'B': filled_counts['B'] += 1
        elif s.level == 'C': filled_counts['C'] += 1

        app = applications_map.get(s.id)
        phone = app.applicant_phone if app and app.applicant_phone else s.phone
        assigned_staff_with_att.append({
            'staff': s,
            'phone': phone,
            'attendance': attendance_map.get(s.pk)
        })

    # Clean up coat counts with 0
    coat_counts = {k: v for k, v in coat_counts.items() if v > 0}

    context = {
        'booking': booking,
        'all_staff': all_staff,
        'grouped_staff': grouped_staff,
        'coat_counts': coat_counts,
        'filled_counts': filled_counts,
        'total_filled': len(assigned_staff_with_att),
        'attendance_map': attendance_map,
        'assigned_staff_with_att': assigned_staff_with_att,
        'payments': payments,
        'pending_applications': pending_applications,
        'cancel_requests': cancel_requests,
        'today': timezone.now().date(),
        'page': 'bookings',
        'captain_tasks': booking.tasks.all().order_by('id'),
    }
    return render(request, 'admin/booking_detail.html', context)


@admin_required
def download_attendance(request, pk):
    from django.http import HttpResponse
    from .pdf_utils import build_attendance_pdf

    booking        = get_object_or_404(Booking, pk=pk)
    attendances    = booking.staff_attendance.filter(date=booking.event_date).select_related('staff')
    assigned_staff = booking.assigned_to.all()
    attendance_map  = {att.staff_id: att for att in attendances}
    applications_map = {app.staff_id: app for app in booking.applications.all()}

    buffer = build_attendance_pdf(booking, assigned_staff, attendance_map, applications_map, generated_by="Admin")

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="attendance_booking_{booking.pk}.pdf"'
    return response


@admin_required
def handle_application(request, pk, app_id, action):
    from django.core.cache import cache
    if request.method != 'POST':
        return redirect('admin_booking_detail', pk=pk)
    application = get_object_or_404(EventApplication, pk=app_id, booking_id=pk)
    if action == 'approve_app':
        if application.status != 'pending':
            messages.error(request, 'Application is no longer pending.')
        else:
            application.status = 'approved'
            application.save()
            application.booking.assigned_to.add(application.staff)
            # Fix 1: Clear staff dashboard cache so they see the update immediately
            cache.delete(f'staff_dash_stats_v2_{application.staff_id}')
            messages.success(request, f'{application.staff.full_name} approved and assigned to event.')
    elif action == 'reject_app':
        if application.status != 'pending':
            messages.error(request, 'Application is no longer pending.')
        else:
            application.status = 'rejected'
            application.save()
            cache.delete(f'staff_dash_stats_v2_{application.staff_id}')
            messages.success(request, 'Application rejected.')
    elif action == 'approve_cancel':
        if application.status != 'cancel_requested':
            messages.error(request, 'No cancel request to approve.')
        else:
            application.status = 'cancelled'
            application.save()
            application.booking.assigned_to.remove(application.staff)
            cache.delete(f'staff_dash_stats_v2_{application.staff_id}')
            messages.success(request, f'Cancel request approved. {application.staff.full_name} removed from event.')
    elif action == 'reject_cancel':
        if application.status != 'cancel_requested':
            messages.error(request, 'No cancel request to reject.')
        else:
            application.status = 'approved'
            application.cancel_rejected = True
            application.save()
            cache.delete(f'staff_dash_stats_v2_{application.staff_id}')
            messages.success(request, 'Cancel request rejected.')

    from django.http import JsonResponse
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Return updated quota counts so the frontend can refresh counts without page reload
        booking = application.booking
        quota_data = {
            'captain': {
                'q': booking.quota_captain,
                'c': booking.applications.filter(status='approved', staff__level='captain').count()
            },
            'a': {
                'q': booking.quota_a,
                'c': booking.applications.filter(status='approved', staff__level='A').count()
            },
            'b': {
                'q': booking.quota_b,
                'c': booking.applications.filter(status='approved', staff__level='B').count()
            },
            'c': {
                'q': booking.quota_c,
                'c': booking.applications.filter(status='approved', staff__level='C').count()
            },
        }
        return JsonResponse({'status': 'success', 'quota': quota_data})

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('admin_booking_detail', pk=pk)



@admin_required
def admin_create_booking(request):
    if request.method == 'POST':
        try:
            # Fix 4: Warn if event date is in the past
            from datetime import date as date_type
            event_date_str = request.POST.get('event_date', '')
            if event_date_str:
                try:
                    event_date_val = date_type.fromisoformat(event_date_str)
                    if event_date_val < date_type.today():
                        messages.warning(request, f'⚠️ Note: The event date {event_date_val.strftime("%d %b %Y")} is in the past.')
                except ValueError:
                    pass
            booking = Booking.objects.create(
                name        = request.POST['name'],
                email       = request.POST.get('email', ''),
                phone       = request.POST['phone'],
                company     = request.POST.get('company', ''),
                event_type  = request.POST['event_type'],
                event_date  = request.POST['event_date'],
                session     = request.POST.get('session', 'day'),
                event_time  = request.POST.get('event_time') or None,
                venue       = request.POST.get('venue', ''),
                location_name = request.POST.get('location_name', ''),
                location_link = request.POST.get('location_link', ''),
                guest_count = int(request.POST.get('guest_count', 1)),
                budget      = request.POST.get('budget') or None,
                dietary_requirements = request.POST.get('dietary_requirements', ''),
                special_requests     = request.POST.get('special_requests', ''),
                message              = request.POST.get('message', ''),
                status               = 'confirmed',  # Manual admin entry defaults to confirmed
                # Note: quoted_price is NOT set from budget — set it separately in booking detail
                allow_direct_join    = request.POST.get('allow_direct_join') == 'on',
                is_long_work         = request.POST.get('is_long_work') == 'on'
            )
            # Admin creating booking is not necessarily assigning themselves, but we can assign later
            messages.success(request, f'Booking for {booking.name} created successfully!')
            return redirect('admin_booking_detail', pk=booking.pk)
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
            
    return render(request, 'admin/create_booking.html', {
        'page': 'bookings',
    })


@admin_required
def admin_edit_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if request.method == 'POST':
        try:
            booking.name = request.POST.get('name', booking.name)
            booking.email = request.POST.get('email', '')
            booking.phone = request.POST.get('phone', booking.phone)
            booking.company = request.POST.get('company', '')
            booking.event_type = request.POST.get('event_type', booking.event_type)
            booking.event_date = request.POST.get('event_date', booking.event_date)
            booking.session = request.POST.get('session', 'day')
            booking.event_time = request.POST.get('event_time') or None
            booking.venue = request.POST.get('venue', '')
            booking.location_name = request.POST.get('location_name', '')
            booking.location_link = request.POST.get('location_link', '')
            booking.guest_count = int(request.POST.get('guest_count', 1))
            booking.budget = request.POST.get('budget') or None
            booking.dietary_requirements = request.POST.get('dietary_requirements', '')
            booking.message = request.POST.get('message', '')
            
            # Quotas & Locality
            booking.quota_captain = int(request.POST.get('quota_captain') or 0)
            booking.quota_a = int(request.POST.get('quota_a') or 0)
            booking.quota_b = int(request.POST.get('quota_b') or 0)
            booking.quota_c = int(request.POST.get('quota_c') or 0)
            booking.publish_locality = request.POST.get('publish_locality', 'all')
            booking.allow_direct_join = request.POST.get('allow_direct_join') == 'on'
            booking.is_long_work = request.POST.get('is_long_work') == 'on'
            
            booking.save()
            messages.success(request, f'Booking #{booking.pk} details and quotas have been updated!')
            return redirect('admin_booking_detail', pk=booking.pk)
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
            
    return render(request, 'admin/edit_booking.html', {
        'booking': booking,
        'page': 'bookings',
    })


@admin_required
def admin_publish_booking(request, pk):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        action = request.POST.get('action', 'publish')
        
        if action == 'publish':
            booking.is_published = True
            booking.publish_locality = request.POST.get('publish_locality', 'all')
            booking.save(update_fields=['is_published', 'publish_locality'])
            if booking.publish_locality != 'all':
                messages.success(request, f'Booking #{booking.pk} has been published EXCLUSIVELY to {booking.publish_locality} staff!')
            else:
                messages.success(request, f'Booking #{booking.pk} has been published to ALL Staff!')
        elif action == 'unpublish':
            booking.is_published = False
            booking.save(update_fields=['is_published'])
            messages.success(request, f'Booking #{booking.pk} is now hidden from the Staff Dashboard.')
            
        return redirect('admin_booking_detail', pk=booking.pk)
    return redirect('admin_bookings')


@admin_required
def update_booking_status(request, pk):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(Booking.STATUS_CHOICES):
            old_status = booking.status
            booking.status = new_status
            booking.save()
            # If status changes TO or FROM completed, recalculate staff totals
            if (old_status == 'completed' or new_status == 'completed') and old_status != new_status:
                for s in booking.assigned_to.all():
                    s.total_events_completed = s.bookings.filter(status='completed').count()
                    s.save(update_fields=['total_events_completed'])
                    if s.level == 'C':
                        day_count = s.bookings.filter(status='completed', session='day').count()
                        night_count = s.bookings.filter(status='completed', session='night').count()
                        long_work_count = s.bookings.filter(status='completed', is_long_work=True).count()
                        if day_count >= 10 and night_count >= 5 and long_work_count >= 5:
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
    from django.utils import timezone
    booking_id = request.GET.get('booking_id')
    
    pending_apps = EventApplication.objects.filter(status='pending').select_related('staff', 'booking').order_by('-created_at')
    cancel_reqs = EventApplication.objects.filter(status='cancel_requested').select_related('staff', 'booking').order_by('-created_at')
    
    if booking_id:
        pending_apps = pending_apps.filter(booking_id=booking_id)
        cancel_reqs = cancel_reqs.filter(booking_id=booking_id)
        
        selected_booking_obj = Booking.objects.get(pk=booking_id)
        live_quota_data = {
            'captain': {'q': selected_booking_obj.quota_captain, 'c': selected_booking_obj.applications.filter(status='approved', staff__level='captain').count()},
            'a': {'q': selected_booking_obj.quota_a, 'c': selected_booking_obj.applications.filter(status='approved', staff__level='A').count()},
            'b': {'q': selected_booking_obj.quota_b, 'c': selected_booking_obj.applications.filter(status='approved', staff__level='B').count()},
            'c': {'q': selected_booking_obj.quota_c, 'c': selected_booking_obj.applications.filter(status='approved', staff__level='C').count()},
        }
    else:
        live_quota_data = None
        
    # Evaluate double shifts
    pending_apps_annotated = []
    for app in pending_apps:
        # Check if they have an earlier application on the same date
        other_app_earlier = EventApplication.objects.filter(
            staff=app.staff,
            booking__event_date=app.booking.event_date,
            status__in=['pending', 'approved'],
            created_at__lt=app.created_at
        ).exclude(pk=app.pk).first()
        
        # Edge case: Check if they are manually assigned to another booking without an application
        other_booking_manual = None
        for b in app.staff.bookings.filter(event_date=app.booking.event_date).exclude(pk=app.booking.pk):
            if not EventApplication.objects.filter(staff=app.staff, booking=b).exists():
                other_booking_manual = b
                break
        
        app.has_double_shift = False
        app.double_shift_event = None
        
        if other_booking_manual:
            app.has_double_shift = True
            app.double_shift_event = f"{other_booking_manual.name} ({other_booking_manual.get_session_display()})"
        elif other_app_earlier:
            app.has_double_shift = True
            app.double_shift_event = f"{other_app_earlier.booking.name} ({other_app_earlier.booking.get_session_display()})"
        
        pending_apps_annotated.append(app)
        
    active_bookings = Booking.objects.filter(status__in=['pending', 'confirmed'], event_date__gte=timezone.now().date()).order_by('event_date')
    
    context = {
        'pending_apps': pending_apps_annotated,
        'cancel_reqs': cancel_reqs,
        'active_bookings': active_bookings,
        'selected_booking': booking_id,
        'live_quota_data': live_quota_data,
        'page': 'staff_requests',
    }
    return render(request, 'admin/staff_requests.html', context)


@admin_required
def staff_applications(request):
    applications = StaffApplication.objects.filter(status='pending').order_by('-created_at')
    context = {
        'applications': applications,
        'page': 'staff_applications',
    }
    return render(request, 'admin/staff_applications.html', context)

@admin_required
def handle_staff_application(request, pk, action):
    application = get_object_or_404(StaffApplication, pk=pk)
    if action == 'approve':
        try:
            from staff.models import generate_staff_id
            new_id = generate_staff_id()
            
            # Create Staff user with default password — must change on first login
            Staff.objects.create_user(
                staff_id=new_id,
                password='password123',
                full_name=application.full_name,
                level='C',
                phone=application.phone_1,
                phone_2=application.phone_2,
                email=application.email,
                date_of_birth=application.date_of_birth,
                gender=application.gender,
                height=application.height,
                blood_group=application.blood_group,
                guardian_name=application.guardian_name,
                guardian_phone=application.guardian_phone,
                main_locality=application.main_locality,
                coat_size=application.coat_size,
                home_address=application.home_address,
                education=application.education,
                must_change_password=True,   # Force password change on first login
            )
            
            application.status = 'approved'
            application.save()
            messages.success(request, f'✅ Staff created! ID: {new_id} | Default Password: password123 — Staff must change it on first login.')
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
    
    # Fix N+1 queries for revenue and payouts on the staff listing
    staff_ids = [s.pk for s in page_obj.object_list]
    from django.db.models import Sum
    from staff.models import StaffPayout
    
    revenue_stats = Staff.objects.filter(
        pk__in=staff_ids, 
        bookings__status__in=['confirmed', 'completed']
    ).values('pk').annotate(total_rev=Sum('bookings__quoted_price'))
    revenue_map = {item['pk']: item['total_rev'] for item in revenue_stats}
    

    payout_stats = StaffPayout.objects.filter(staff_id__in=staff_ids).values('staff_id', 'status').annotate(total=Sum('amount'))
    paid_map = {}
    pending_map = {}
    for item in payout_stats:
        if item['status'] == 'paid':
            paid_map[item['staff_id']] = item['total']
        elif item['status'] == 'pending':
            pending_map[item['staff_id']] = item['total']

    for s in page_obj.object_list:
        s.annotated_revenue = revenue_map.get(s.pk, 0) or 0
        s.annotated_paid_out = paid_map.get(s.pk, 0) or 0
        s.annotated_pending_payout = pending_map.get(s.pk, 0) or 0

    total_staff_count = Staff.objects.filter(is_active=True).count()
    total_events_served = Booking.objects.filter(status='completed').count()

    context = {
        'staff': page_obj,
        'page': 'staff',
        'total_events_served': total_events_served,
        'total_staff_count': total_staff_count,
    }
    return render(request, 'admin/staff_list.html', context)


@admin_required
def staff_add(request):
    if request.method == 'POST':
        from core.utils import validate_phone
        full_name = request.POST.get('full_name', '').strip()
        level = request.POST.get('level', 'C')
        phone_raw = request.POST.get('phone', '')
        phone_2_raw = request.POST.get('phone_2', '')
        guardian_phone_raw = request.POST.get('guardian_phone', '')

        # Phone validation
        phone = validate_phone(phone_raw)
        if not phone:
            messages.error(request, f'Invalid phone number: "{phone_raw}". Please enter a valid 10-digit Indian mobile number.')
            return render(request, 'admin/staff_add.html', {'page': 'staff', 'form_data': request.POST})

        phone_2 = validate_phone(phone_2_raw) or phone_2_raw  # Alt phone is optional
        guardian_phone = validate_phone(guardian_phone_raw)
        if guardian_phone_raw and not guardian_phone:
            messages.error(request, f'Invalid guardian phone: "{guardian_phone_raw}". Please enter a valid 10-digit number.')
            return render(request, 'admin/staff_add.html', {'page': 'staff', 'form_data': request.POST})

        # Defensive parsing
        try:
            daily_rate = float(request.POST.get('daily_rate', 0) or 0)
        except (ValueError, TypeError):
            daily_rate = 0

        email = request.POST.get('email', '')
        date_of_birth = request.POST.get('date_of_birth') or None
        gender = request.POST.get('gender', '')
        height = request.POST.get('height', '')
        blood_group = request.POST.get('blood_group', '')
        guardian_name = request.POST.get('guardian_name', '')
        main_locality = request.POST.get('main_locality', '')
        coat_size = request.POST.get('coat_size') or None
        home_address = request.POST.get('home_address', '')
        education = request.POST.get('education', '')

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
                date_of_birth=date_of_birth,
                gender=gender,
                height=height,
                blood_group=blood_group,
                guardian_name=guardian_name,
                guardian_phone=guardian_phone or '',
                main_locality=main_locality,
                coat_size=coat_size,
                home_address=home_address,
                education=education,
                must_change_password=True,  # Force password change on first login
            )
            messages.success(request, f'✅ Staff added! ID: {member.staff_id} — Share login credentials privately. They must change their password on first login.')
            return redirect('admin_staff')
        except Exception as e:
            messages.error(request, f'Error adding staff: {str(e)}')
            return render(request, 'admin/staff_add.html', {
                'page': 'staff',
                'form_data': request.POST
            })

    return render(request, 'admin/staff_add.html', {'page': 'staff'})


@admin_required
def staff_edit(request, pk):
    from core.utils import validate_phone
    member = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'reset_password':
            member.set_password('password123')
            member.must_change_password = True
            member.save(update_fields=['password', 'must_change_password'])
            messages.success(request, f"Password carefully reset to 'password123' for {member.full_name}. They must change it upon login.")
            return redirect('admin_staff_detail', pk=member.pk)
            
        phone_raw = request.POST.get('phone', '')
        phone = validate_phone(phone_raw)
        if not phone:
            messages.error(request, f'Invalid phone number: "{phone_raw}". Please enter a valid 10-digit mobile number.')
            return render(request, 'admin/staff_edit.html', {'member': member, 'page': 'staff'})

        member.full_name = request.POST['full_name']
        member.level = request.POST['level']
        member.daily_rate = request.POST.get('daily_rate', 0)
        member.phone = phone
        member.phone_2 = validate_phone(request.POST.get('phone_2', '')) or request.POST.get('phone_2', '')
        member.email = request.POST.get('email', '')
        member.date_of_birth = request.POST.get('date_of_birth') or None
        member.gender = request.POST.get('gender', '')
        member.height = request.POST.get('height', '')
        member.blood_group = request.POST.get('blood_group', '')
        member.guardian_name = request.POST.get('guardian_name', '')
        member.guardian_phone = request.POST.get('guardian_phone', '')
        member.main_locality = request.POST.get('main_locality', '')
        member.coat_size = request.POST.get('coat_size') or None
        member.home_address = request.POST.get('home_address', '')
        member.education = request.POST.get('education', '')
        member.is_active = request.POST.get('is_active') == 'on'
        member.save()
        messages.success(request, f'Staff {member.full_name} updated successfully!')
        return redirect('admin_staff_detail', pk=member.pk)

    return render(request, 'admin/staff_edit.html', {'member': member, 'page': 'staff'})



@admin_required
def staff_detail(request, pk):
    member = get_object_or_404(Staff.objects.prefetch_related('bookings', 'payouts'), pk=pk)
    today  = timezone.now().date()

    # Performance Fix 7: Optimization for staff_detail (limit and prefetch already handled by related_name queries)
    bookings   = member.bookings.all().order_by('-event_date')[:10]
    payouts    = member.payouts.all().order_by('-created_at')
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
        'bookings': bookings,
        'payouts': payouts,
        'revenue': revenue,
        'total_paid': total_paid,
        'pending': pending,
        'today': today,
        'page': 'staff',
        'pending_count': get_pending_count(),
    }
    return render(request, 'admin/staff_detail.html', context)


@admin_required
def mark_payout_paid(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
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
}
    return render(request, 'admin/menu.html', context)


@admin_required
def menu_add(request):
    if request.method == 'POST':
        category_id = request.POST.get('category')
        new_category = request.POST.get('new_category', '').strip()
        
        if new_category:
            cat, _ = MenuCategory.objects.get_or_create(name=new_category)
            category_id = cat.id

        MenuItem.objects.create(
            category_id   = category_id,
            name          = request.POST['name'],
            description   = request.POST['description'],
            price         = request.POST['price'],
            is_vegetarian = request.POST.get('is_vegetarian') == 'on',
            is_vegan      = request.POST.get('is_vegan') == 'on',
            is_gluten_free= request.POST.get('is_gluten_free') == 'on',
            is_featured   = request.POST.get('is_featured') == 'on',
            is_available  = request.POST.get('is_available', 'on') in ['on', True, 'true'],
        )
        if 'image' in request.FILES and request.FILES['image']:
            item.image = request.FILES['image']
            item.save()
        messages.success(request, 'Menu item added!')
        return redirect('admin_menu')
    categories = MenuCategory.objects.all()
    return render(request, 'admin/menu_add.html', {
        'categories': categories, 'page': 'menu',
    })


@admin_required
def menu_edit(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        category_id = request.POST.get('category')
        new_category = request.POST.get('new_category', '').strip()
        
        if new_category:
            cat, _ = MenuCategory.objects.get_or_create(name=new_category)
            category_id = cat.id

        item.category_id = category_id
        item.name = request.POST['name']
        item.description = request.POST['description']
        item.price = request.POST['price']
        item.is_vegetarian = request.POST.get('is_vegetarian') == 'on'
        item.is_vegan = request.POST.get('is_vegan') == 'on'
        item.is_gluten_free = request.POST.get('is_gluten_free') == 'on'
        item.is_featured = request.POST.get('is_featured') == 'on'
        item.is_available = request.POST.get('is_available') == 'on'

        if 'image' in request.FILES and request.FILES['image']:
            item.image = request.FILES['image']
        elif request.POST.get('clear_image') == 'on':
            item.image = None

        item.save()
        messages.success(request, f'"{item.name}" updated successfully!')
        return redirect('admin_menu')
        
    categories = MenuCategory.objects.all()
    return render(request, 'admin/menu_edit.html', {
        'item': item, 'categories': categories, 'page': 'menu',
    })


@admin_required
def menu_delete(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
    item = get_object_or_404(MenuItem, pk=pk)
    item.delete()
    messages.success(request, f'"{item.name}" removed.')
    return redirect('admin_menu')


@admin_required
def menu_category_delete(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
    cat = get_object_or_404(MenuCategory, pk=pk)
    cat_name = cat.name
    cat.delete()
    messages.success(request, f'Category "{cat_name}" and its inner items were removed.')
    return redirect('admin_menu')


@admin_required
def gallery_list(request):
    from gallery.models import GalleryCategory
    images = GalleryImage.objects.order_by('-uploaded_at')
    categories = GalleryCategory.objects.all()
    context = {'images': images, 'categories': categories, 'page': 'gallery',
}
    return render(request, 'admin/gallery.html', context)


@admin_required
def gallery_add(request):
    from gallery.models import GalleryCategory
    if request.method == 'POST':
        category_id = request.POST.get('category')
        new_category = request.POST.get('new_category', '').strip()
        
        if new_category:
            cat, _ = GalleryCategory.objects.get_or_create(name=new_category)
            category_id = cat.id
            
        img = GalleryImage(
            category_id = category_id,
            title       = request.POST['title'],
            description = request.POST.get('description', ''),
            is_featured = request.POST.get('is_featured') == 'on',
        )
        if 'image' in request.FILES:
            img.image = request.FILES['image']
            img.save()
            messages.success(request, 'Gallery image added!')
        else:
            messages.error(request, 'No image file uploaded.')
        return redirect('admin_gallery')
        
    categories = GalleryCategory.objects.all()
    return render(request, 'admin/gallery_add.html', {
        'categories': categories, 'page': 'gallery',
    })


@admin_required
def gallery_edit(request, pk):
    from gallery.models import GalleryCategory
    img = get_object_or_404(GalleryImage, pk=pk)
    if request.method == 'POST':
        category_id = request.POST.get('category')
        new_category = request.POST.get('new_category', '').strip()
        
        if new_category:
            cat, _ = GalleryCategory.objects.get_or_create(name=new_category)
            category_id = cat.id
            
        img.category_id = category_id
        img.title = request.POST['title']
        img.description = request.POST.get('description', '')
        img.is_featured = request.POST.get('is_featured') == 'on'
        
        if 'image' in request.FILES and request.FILES['image']:
            img.image = request.FILES['image']
            
        img.save()
        messages.success(request, f'Gallery image "{img.title}" updated!')
        return redirect('admin_gallery')
        
    categories = GalleryCategory.objects.all()
    return render(request, 'admin/gallery_edit.html', {
        'img': img, 'categories': categories, 'page': 'gallery',
    })


@admin_required
def gallery_delete(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
    img = get_object_or_404(GalleryImage, pk=pk)
    img.delete()
    messages.success(request, 'Gallery image deleted.')
    return redirect('admin_gallery')


@admin_required
def gallery_category_delete(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
    from gallery.models import GalleryCategory
    cat = get_object_or_404(GalleryCategory, pk=pk)
    cat_name = cat.name
    cat.delete()
    messages.success(request, f'Gallery category "{cat_name}" removed.')
    return redirect('admin_gallery')


@admin_required
def team_page(request):
    staff = Staff.objects.filter(is_active=True)
    return render(request, 'admin/team.html', {
        'staff': staff, 'page': 'team',
    })


@admin_required
def staff_promotions(request):
    from staff.models import PromotionRequest
    requests = PromotionRequest.objects.filter(status='pending').order_by('-created_at')
    return render(request, 'admin/staff_promotions.html', {
        'requests': requests,
        'page': 'staff_promotions',
    })


@admin_required
def handle_promotion(request, pk, action):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
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


# ── Manual Reports ────────────────────────────────────────────────────────────

@admin_required
def admin_reports(request):
    from bookings.models import ManualReport
    from django.db.models import Sum
    import calendar
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', '')
    
    reports = ManualReport.objects.all()
    
    month_name = ''
    if month_filter:
        reports = reports.filter(event_date__month=month_filter)
        try:
            month_name = calendar.month_name[int(month_filter)]
        except:
            pass
            
    if year_filter:
        reports = reports.filter(event_date__year=year_filter)
        
    totals = reports.aggregate(
        t_boys=Sum('boys_count'),
        t_bill=Sum('bill_amount'),
        t_received=Sum('amount_received'),
        t_profit=Sum('profit')
    )
        
    context = {
        'reports': reports,
        'totals': totals,
        'page': 'reports',
        'month_filter': month_filter,
        'month_name': month_name,
        'year_filter': year_filter,
    }
    return render(request, 'admin/reports.html', context)

@admin_required
def admin_report_add(request):
    from bookings.models import ManualReport
    if request.method == 'POST':
        try:
            bill_amount = float(request.POST.get('bill_amount') or 0.00)
            amount_received = float(request.POST.get('amount_received') or 0.00)
            
            # Fix 8: Auto-calculate pending_amount
            pending_amount = request.POST.get('pending_amount', '').strip()
            if not pending_amount:
                pending_amount = bill_amount - amount_received

            ManualReport.objects.create(
                event_date = request.POST['event_date'],
                site_name = request.POST.get('site_name', ''),
                event_name = request.POST.get('event_name', ''),
                boys_count = int(request.POST.get('boys_count') or 0),
                bill_incharge = request.POST.get('bill_incharge', ''),
                bill_amount = bill_amount,
                amount_received = amount_received,
                payment_received_on = request.POST.get('payment_received_on') or None,
                pending_amount = pending_amount,
                profit = request.POST.get('profit') or 0.00,
                is_settled = request.POST.get('is_settled') == 'on'
            )
            messages.success(request, 'Report entry added successfully!')
            return redirect('admin_reports')
        except Exception as e:
            messages.error(request, f'Error creating report: {str(e)}')
            
    return render(request, 'admin/report_add.html', {
        'page': 'reports',
    })

@admin_required
def admin_report_delete(request, pk):
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Method not allowed. Use POST.")
    from bookings.models import ManualReport
    report = get_object_or_404(ManualReport, pk=pk)
    report.delete()
    messages.success(request, 'Report entry deleted.')
    return redirect('admin_reports')


@admin_required
def admin_report_edit(request, pk):
    from bookings.models import ManualReport
    report = get_object_or_404(ManualReport, pk=pk)
    if request.method == 'POST':
        try:
            bill_amount = float(request.POST.get('bill_amount') or 0.00)
            amount_received = float(request.POST.get('amount_received') or 0.00)
            
            # Fix 8: Auto-calculate pending_amount
            pending_amount = request.POST.get('pending_amount', '').strip()
            if not pending_amount:
                pending_amount = bill_amount - amount_received

            report.event_date = request.POST['event_date']
            report.site_name = request.POST.get('site_name', '')
            report.event_name = request.POST.get('event_name', '')
            report.boys_count = int(request.POST.get('boys_count') or 0)
            report.bill_incharge = request.POST.get('bill_incharge', '')
            report.bill_amount = bill_amount
            report.amount_received = amount_received
            report.payment_received_on = request.POST.get('payment_received_on') or None
            report.pending_amount = pending_amount
            report.profit = request.POST.get('profit') or 0.00
            report.is_settled = request.POST.get('is_settled') == 'on'
            report.save()
            messages.success(request, 'Report entry updated successfully!')
            return redirect('admin_reports')
        except Exception as e:
            messages.error(request, f'Error updating report: {str(e)}')
            
    return render(request, 'admin/report_edit.html', {
        'report': report,
        'page': 'reports',
    })

@admin_required
def staff_notice(request):
    from staff.models import StaffNotice
    notice = StaffNotice.objects.filter().order_by('-created_at').first()
    
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if notice:
            if notice.message != message or notice.is_active != is_active:
                notice.message = message
                notice.is_active = is_active
                notice.save()
                should_broadcast = is_active
            else:
                should_broadcast = False
        else:
            notice = StaffNotice.objects.create(message=message, is_active=is_active)
            should_broadcast = is_active
            
        if should_broadcast:
            import firebase_admin
            from firebase_admin import messaging
            from staff.models import FCMDevice
            
            if not firebase_admin._apps:
                messages.error(request, "🔥 SERVER ERROR: Firebase Admin is completely missing or broken on the server! Please verify firebase-adminsdk.json is present on the server.")
            else:
                tokens = list(FCMDevice.objects.filter(staff__is_active=True).values_list('token', flat=True))
                if tokens:
                    base_url = "https://mastan.in"
                    body_text = notice.message[:150] + ("..." if len(notice.message) > 150 else "")
                    title = "MASTAN'S CATERING — Official Notice"
                    icon = f"{base_url}/static/images/logo.png"
                    badge = f"{base_url}/static/icons/icon-192x192.png"
                    link = f"{base_url}/staff/"
                    fcm_msg = messaging.MulticastMessage(
                        notification=messaging.Notification(title=title, body=body_text),
                        data={'title': title, 'body': body_text, 'link': link, 'icon': icon},
                        android=messaging.AndroidConfig(
                            priority='high',
                            notification=messaging.AndroidNotification(
                                title=title,
                                body=body_text,
                                icon='ic_notification',
                                color='#D4A852',
                            )
                        ),
                        webpush=messaging.WebpushConfig(
                            headers={"Urgency": "high"},
                            notification=messaging.WebpushNotification(
                                icon=icon,
                                badge=badge,
                                title=title,
                                body=body_text,
                            ),
                            fcm_options=messaging.WebpushFCMOptions(link=link)
                        ),
                        tokens=tokens,
                    )
                    try:
                        response = messaging.send_each_for_multicast(fcm_msg)
                        if response.failure_count > 0:
                            messages.warning(request, f"Notice saved, but Firebase failed to reach {response.failure_count} devices. They might be unregistered.")
                        else:
                            messages.success(request, f"Notice saved & sent to {response.success_count} devices!")
                        stale_tokens = [tokens[i] for i, r in enumerate(response.responses) if not r.success]
                        if stale_tokens:
                            FCMDevice.objects.filter(token__in=stale_tokens).delete()
                    except Exception as e:
                        messages.error(request, f"🔥 FIREBASE API ERROR: {str(e)}")
                else:
                    messages.info(request, "Notice saved, but no staff devices are currently registered for push notifications.")
        else:
            messages.success(request, 'Notice Board updated successfully!')
        return redirect('admin_staff_notice')
        
    return render(request, 'admin/notice.html', {
        'notice': notice,
        'page': 'staff_notice',
    })

@admin_required
def manual_invoice(request):
    return render(request, 'admin/manual_invoice.html', {
        'page': 'reports',
    })


@admin_required
def event_reports_list(request):
    from django.core.paginator import Paginator
    from bookings.models import EventReport
    reports = EventReport.objects.all().select_related('booking', 'submitted_by')
    
    # Simple pagination
    paginator = Paginator(reports, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    return render(request, 'admin/event_reports_list.html', {
        'reports': page_obj,
        'page': 'reports',
    })

@admin_required
def event_report_detail(request, pk):
    from bookings.models import EventReport
    report = get_object_or_404(EventReport, pk=pk)
    return render(request, 'admin/event_report_detail.html', {
        'report': report,
        'page': 'reports',
    })
@admin_required
def download_invoice_pdf(request):
    """
    Handle POST request with invoice JSON data and return a professional PDF.
    """
    if request.method == 'POST':
        import json
        try:
            if 'invoice_data' in request.POST:
                data = json.loads(request.POST.get('invoice_data'))
            else:
                data = json.loads(request.body)
            from .pdf_utils import build_invoice_pdf
            buffer = build_invoice_pdf(data)
            
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            inv_no = data.get('inv_no', 'invoice')
            response['Content-Disposition'] = f'attachment; filename="Invoice_{inv_no}.pdf"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return redirect('admin_manual_invoice')
