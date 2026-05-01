from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
import json

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.db.models import Sum, Q
from django.db import transaction
from django.core.cache import cache

from .models import Staff, StaffAttendance, StaffNotice, FCMDevice
from bookings.models import Booking, BookingPayment, EventApplication
from core.utils import notify_admins
import threading



from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST# ── Firebase ────────────────────────────────────────────────────────────────
@csrf_exempt
@login_required
def save_fcm_token(request):
    """
    Saves or updates the Firebase Cloud Messaging token for the authenticated staff.
    Handles the 'unique=True' constraint by transferring tokens between users if a device changes hands.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            token = data.get('token')
            if not token or not request.user.is_authenticated:
                return JsonResponse({'status': 'error', 'message': 'Invalid token or user not authenticated'}, status=400)

            # Fix: Handle unique=True constraint gracefully.
            # If this token already exists for another user, delete the old record or update it.
            # This prevents IntegrityError when a device is shared or re-assigned.
            existing = FCMDevice.objects.filter(token=token).first()
            if existing:
                if existing.staff != request.user:
                    # Token switched users (e.g. device shared)
                    existing.staff = request.user
                    existing.device_name = request.META.get('HTTP_USER_AGENT', 'Unknown')
                    existing.save()
                else:
                    # Same user, just update last_used
                    existing.device_name = request.META.get('HTTP_USER_AGENT', 'Unknown')
                    existing.save()
            else:
                # New token entirely
                FCMDevice.objects.create(
                    staff=request.user,
                    token=token,
                    device_name=request.META.get('HTTP_USER_AGENT', 'Unknown')
                )

            return JsonResponse({'status': 'success'})
        except Exception as e:
            # Fallback debug log
            try:
                with open('/tmp/fcm_error.log', 'a') as f:
                    import datetime
                    f.write(f"[{datetime.datetime.now()}] Error: {str(e)}\n")
            except: pass
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalid method'}, status=405)


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
            # Clear the first-login flag if it was set
            if user.must_change_password:
                user.must_change_password = False
                user.save(update_fields=['must_change_password'])
            messages.success(request, 'Your password was successfully updated!')
            return redirect('staff_dashboard')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    is_forced = request.user.must_change_password
    return render(request, 'staff/password_change.html', {
        'form': form,
        'is_forced': is_forced,
    })

def staff_login(request):
    """Authenticates and logs in a staff member using their staff ID."""
    if request.user.is_authenticated:
        # Already logged in — check if password change is required
        if request.user.must_change_password:
            return redirect('staff_change_password')
        return redirect('staff_dashboard')
    if request.method == 'POST':
        staff_id = request.POST.get('staff_id', '').strip().upper()
        password = request.POST.get('password', '')
        user = authenticate(request, username=staff_id, password=password)
        if user and user.is_active:
            login(request, user)
            # Make session permanent (1 year)
            request.session.set_expiry(60 * 60 * 24 * 365)
            # Force password change for new staff on first login
            if user.must_change_password:
                messages.warning(request, 
                    '⚠️ You must change your default password before continuing.')
                return redirect('staff_change_password')
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
    from core.pdf_utils import build_attendance_pdf

    me = request.user
    if me.level not in ['captain', 'supervisor']:
        messages.error(request, 'Only Captains can download PDF reports.')
        return redirect('staff_booking_detail', pk=pk)

    booking = get_object_or_404(Booking, pk=pk)

    # Check access
    is_assigned = booking.assigned_to.filter(id=me.id).exists()
    if not is_assigned and not me.is_staff:
        messages.error(request, 'You do not have access to this booking.')
        return redirect('staff_bookings')

    attendances      = booking.staff_attendance.filter(date=booking.event_date).select_related('staff')
    assigned_staff   = booking.assigned_to.all()
    attendance_map   = {att.staff_id: att for att in attendances}
    applications_map = {app.staff_id: app for app in booking.applications.all()}

    buffer = build_attendance_pdf(
        booking, assigned_staff, attendance_map, applications_map,
        generated_by=f"Captain: {me.full_name}"
    )

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="attendance_booking_{booking.pk}.pdf"'
    return response




# ── Staff Dashboard ──────────────────────────────────────────────────────────

from django.core.cache import cache
from core.utils import auto_complete_past_bookings

@login_required(login_url='/staff/login/')
def staff_dashboard(request):
    """Renders the main dashboard showing personal data, upcoming bookings, and payout summaries."""
    # Block dashboard access if first-login password change is pending
    if request.user.must_change_password:
        messages.warning(request, '⚠️ Please change your default password first.')
        return redirect('staff_change_password')

    # Auto-complete past events before loading stats
    auto_complete_past_bookings()
    
    me = request.user
    today = timezone.now().date()

    my_bookings   = me.bookings.all()
    my_created    = me.bookings_created.all()
    
    upcoming      = my_bookings.filter(event_date__gte=today, status='confirmed').order_by('event_date')[:5]
    recent        = my_created.order_by('-created_at')[:5]
    my_payouts    = me.payouts.order_by('-created_at')[:5]

    cache_key = f'staff_dash_stats_v2_{me.pk}'
    cached_stats = cache.get(cache_key)

    if not cached_stats:
        pending_count = my_bookings.filter(status='pending').count()
        my_revenue    = my_bookings.filter(status__in=['confirmed','completed']).aggregate(t=Sum('quoted_price'))['t'] or 0
        total_earned  = me.payouts.filter(status='paid').aggregate(t=Sum('amount'))['t'] or 0
        pending_pay   = me.payouts.filter(status='pending').aggregate(t=Sum('amount'))['t'] or 0
        
        my_applications = me.event_applications.all()
        pending_app_booking_ids = list(my_applications.filter(status='pending').values_list('booking_id', flat=True))
        cancel_req_booking_ids = list(my_applications.filter(status='cancel_requested').values_list('booking_id', flat=True))
        rejected_app_booking_ids = list(my_applications.filter(status='rejected').values_list('booking_id', flat=True))
        cancelled_app_booking_ids = list(my_applications.filter(status='cancelled').values_list('booking_id', flat=True))
        cancel_rejected_booking_ids = list(my_applications.filter(status='approved', cancel_rejected=True).values_list('booking_id', flat=True))

        day_works = my_bookings.filter(status='completed', session='day').count()
        night_works = my_bookings.filter(status='completed', session='night').count()
        long_works = my_bookings.filter(status='completed', is_long_work=True).count()
        
        cached_stats = {
            'pending_count': pending_count,
            'my_revenue': my_revenue,
            'total_earned': total_earned,
            'pending_pay': pending_pay,
            'pending_app_booking_ids': pending_app_booking_ids,
            'cancel_req_booking_ids': cancel_req_booking_ids,
            'rejected_app_booking_ids': rejected_app_booking_ids,
            'cancelled_app_booking_ids': cancelled_app_booking_ids,
            'cancel_rejected_booking_ids': cancel_rejected_booking_ids,
            'day_works': day_works,
            'night_works': night_works,
            'long_works': long_works,
            'total_bookings': my_bookings.count(),
            'confirmed_count': my_bookings.filter(status='confirmed').count(),
            'completed_count': my_bookings.filter(status='completed').count(),
        }
        cache.set(cache_key, cached_stats, 300) # Increased to 5 minutes for "pacha vellum" flow
        
    # Calculate Published Bookings Quota dynamic availability (already optimized with prefetch)
    available_bookings_qs = Booking.objects.filter(
        status__in=['pending', 'confirmed'], 
        event_date__gte=today,
        is_published=True
    ).exclude(assigned_to=me).prefetch_related('applications__staff', 'assigned_to').order_by('event_date', 'event_time')
    
    available_bookings = []
    for b in available_bookings_qs:
        # 1. Level-specific Quota Check: Only show if there's a quota for user's level
        level_quota = 0
        if me.level == 'captain':
            level_quota = b.quota_captain
        elif me.level == 'supervisor':
            level_quota = b.quota_supervisor
        elif me.level == 'A':
            level_quota = b.quota_a
        elif me.level == 'B':
            level_quota = b.quota_b
        elif me.level == 'C':
            level_quota = b.quota_c
        
        # If no quota is set for this staff's level, hide the event (as per user's "mandatory quota" logic)
        if level_quota <= 0:
            continue

        # Locality filter
        if b.publish_locality != 'all' and me.main_locality != b.publish_locality:
            continue
            
        if len(available_bookings) >= 20:
            break
            
        # 2. Accurate Filled Count: Include both approved apps AND manual assignments
        # Use sets to avoid double counting if a staff is in both
        working_staff_ids = set([s.id for s in b.assigned_to.all() if s.level == me.level])
        approved_app_staff_ids = set([app.staff_id for app in b.applications.all() if app.status == 'approved' and app.staff.level == me.level])
        total_filled_for_level = len(working_staff_ids | approved_app_staff_ids)
        
        is_full = total_filled_for_level >= level_quota
        b.is_level_full = is_full
        available_bookings.append(b)

    rem_day, rem_night, rem_long = 0, 0, 0
    if me.level == 'C':
        rem_day = max(0, 10 - cached_stats.get('day_works', 0))
        rem_night = max(0, 5 - cached_stats.get('night_works', 0))
        rem_long = max(0, 5 - cached_stats.get('long_works', 0))

    latest_promotion = me.promotion_requests.order_by('-created_at').first()
    latest_notice = StaffNotice.objects.order_by('-created_at').first()
    active_notice = latest_notice if latest_notice and latest_notice.is_active else None

    return render(request, 'staff/dashboard.html', {
        'me': me,
        **cached_stats,
        'upcoming': upcoming,
        'available_bookings': available_bookings,
        'recent_bookings': recent,
        'pending_count': cached_stats.get('pending_count', 0),
        'my_payouts': my_payouts,
        'rem_day': rem_day,
        'rem_night': rem_night,
        'rem_long': rem_long,
        'latest_promotion': latest_promotion,
        'active_notice': active_notice,
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
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(venue__icontains=search) |
            Q(location_name__icontains=search)
        )

    from django.db.models import Case, When, IntegerField, Value
    bookings = bookings.select_related('created_by').prefetch_related(
        'applications__staff', 'assigned_to'
    ).annotate(
        # Completed events get sort_order=1, everything else gets 0 (comes first)
        sort_order=Case(
            When(status='completed', then=Value(1)),
            When(status='cancelled', then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by('sort_order', 'event_date')

    paginator = Paginator(bookings, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # AJAX request — return JSON with rendered rows
    if request.GET.get('ajax') == '1':
        from django.template.loader import render_to_string
        rows_html = render_to_string('staff/_bookings_rows.html', {'bookings': page_obj}, request=request)
        pagination_html = render_to_string('pagination.html', {'page_obj': page_obj}, request=request)
        return JsonResponse({'html': rows_html, 'pagination_html': pagination_html})

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
                email       = request.POST['email'],
                phone       = request.POST['phone'],
                company     = request.POST.get('company', ''),
                event_type  = request.POST['event_type'],
                event_date  = request.POST['event_date'],
                event_time  = request.POST.get('event_time') or None,
                venue       = request.POST.get('venue', ''),
                guest_count = int(request.POST.get('guest_count', 1)),
                session     = request.POST.get('session', 'day'),
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
        Booking.objects.select_related('created_by'),
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
            amount_str = request.POST.get('amount', '').strip()
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError('Amount must be positive')
            except (ValueError, TypeError):
                messages.error(request, f'Invalid payment amount: "{amount_str}". Please enter a valid positive number.')
                return redirect('staff_booking_detail', pk=pk)

            BookingPayment.objects.create(
                booking     = booking,
                amount      = amount,
                method      = request.POST['method'],
                reference   = request.POST.get('reference', ''),
                received_on = request.POST['received_on'],
                received_by = me,
                notes       = request.POST.get('notes', ''),
            )
            messages.success(request, f'Payment of ₹{amount} recorded!')
            return redirect('staff_booking_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'Error recording payment: {e}')

    if request.method == 'POST' and request.POST.get('action') == 'mark_attendance':
        # Attendance is now handled via AJAX in staff/booking_detail.html
        pass

    assigned_staff_list = []
    attendances = StaffAttendance.objects.filter(booking=booking, date=booking.event_date).select_related('staff')
    att_map = {a.staff_id: a for a in attendances}
    applications_map = {app.staff_id: app for app in booking.applications.filter(status__in=['approved', 'pending']).select_related('staff')}

    for s in booking.assigned_to.select_related():
        app = applications_map.get(s.id)
        phone = s.phone
        assigned_staff_list.append({
            'staff': s,
            'phone': phone,
            'attendance': att_map.get(s.id)
        })

    # Captain Tasks Logic
    booking.generate_default_tasks()
    captain_tasks = booking.tasks.all().order_by('id')

    return render(request, 'staff/booking_detail.html', {
        'me': me,
        'booking': booking,
        'payments': payments,
        'today': timezone.now().date(),
        'assigned_staff_list': assigned_staff_list,
        'captain_tasks': captain_tasks,
    })


@login_required(login_url='/staff/login/')
def staff_apply_booking(request, pk):
    """Handles staff applications to work on available, confirmed upcoming bookings."""
    booking = get_object_or_404(Booking, pk=pk, status__in=['pending', 'confirmed'], is_published=True)
    
    if booking.publish_locality != 'all' and request.user.main_locality != booking.publish_locality:
        messages.error(request, "This event is currently only open for staff from " + booking.publish_locality + ".")
        return redirect('staff_dashboard')
    
    approved_count = booking.applications.filter(status='approved', staff__level=request.user.level).count()
    is_full = False
    
    if request.user.level == 'captain':
        if booking.quota_captain > 0 and approved_count >= booking.quota_captain:
            is_full = True
    elif request.user.level == 'supervisor':
        if booking.quota_supervisor > 0 and approved_count >= booking.quota_supervisor:
            is_full = True
    elif request.user.level == 'A':
        if booking.quota_a > 0 and approved_count >= booking.quota_a:
            is_full = True
    elif request.user.level == 'B':
        if booking.quota_b > 0 and approved_count >= booking.quota_b:
            is_full = True
    elif request.user.level == 'C':
        if booking.quota_c > 0 and approved_count >= booking.quota_c:
            is_full = True

    if is_full:
        messages.error(request, f"Sorry, the {request.user.get_level_display()} quota is fully booked for this event.")
        return redirect('staff_dashboard')

    # --- DOUBLE WORK DETECTION ---
    # Check if staff already has a booking on the same event_date (any session / any assignment)
    same_day_apps = EventApplication.objects.filter(
        staff=request.user,
        booking__event_date=booking.event_date,
        status__in=['pending', 'approved', 'cancel_requested']
    ).exclude(booking=booking).exists()

    same_day_assigned = request.user.bookings.filter(
        event_date=booking.event_date,
        status__in=['pending', 'confirmed']
    ).exclude(pk=booking.pk).exists()

    is_double_work = same_day_apps or same_day_assigned

    # If GET, render a simple apply form
    if request.method == 'GET':
        from core.models import TermAndCondition
        terms = TermAndCondition.objects.all()
        return render(request, 'staff/apply_booking.html', {
            'booking': booking,
            'user': request.user,
            'is_double_work': is_double_work,
            'terms': terms,
        })
    
    # If POST, process the application
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Lock the booking row for the duration of this transaction to prevent quota race conditions
                booking = Booking.objects.select_for_update().get(pk=pk)
                
                approved_count = booking.applications.filter(status='approved', staff__level=request.user.level).count()
                is_full = False
                
                if request.user.level == 'captain':
                    if booking.quota_captain > 0 and approved_count >= booking.quota_captain:
                        is_full = True
                elif request.user.level == 'supervisor':
                    if booking.quota_supervisor > 0 and approved_count >= booking.quota_supervisor:
                        is_full = True
                elif request.user.level == 'A':
                    if booking.quota_a > 0 and approved_count >= booking.quota_a:
                        is_full = True
                elif request.user.level == 'B':
                    if booking.quota_b > 0 and approved_count >= booking.quota_b:
                        is_full = True
                elif request.user.level == 'C':
                    if booking.quota_c > 0 and approved_count >= booking.quota_c:
                        is_full = True

                if is_full:
                    messages.error(request, f"Sorry, the {request.user.get_level_display()} quota is fully booked for this event.")
                    return redirect('staff_dashboard')

                # --- SHIFT CONSTRAINT VALIDATION ---
                # A staff member cannot have 2 pending/approved applications OR direct assignments 
                # on the exact same date for the exact same session (Day/Day or Night/Night).
                conflicting_apps = EventApplication.objects.filter(
                    staff=request.user,
                    booking__event_date=booking.event_date,
                    booking__session=booking.session,
                    status__in=['pending', 'approved', 'cancel_requested']
                ).exclude(booking=booking).exists()
                
                conflicting_assigned = request.user.bookings.filter(
                    event_date=booking.event_date,
                    session=booking.session,
                    status__in=['pending', 'confirmed']
                ).exclude(pk=booking.pk).exists()
                
                if conflicting_apps or conflicting_assigned:
                    messages.error(request, f"You already have a {booking.get_session_display()} shift on {booking.event_date.strftime('%d %b')}. You cannot apply for the same session twice.")
                    return redirect('staff_dashboard')
                # -----------------------------------

                # --- RE-CHECK DOUBLE WORK (for POST) ---
                same_day_apps_post = EventApplication.objects.filter(
                    staff=request.user,
                    booking__event_date=booking.event_date,
                    status__in=['pending', 'approved', 'cancel_requested']
                ).exclude(booking=booking).exists()
                same_day_assigned_post = request.user.bookings.filter(
                    event_date=booking.event_date,
                    status__in=['pending', 'confirmed']
                ).exclude(pk=booking.pk).exists()
                is_double_work_post = same_day_apps_post or same_day_assigned_post
                # ----------------------------------------
                
                applicant_name = request.POST.get('applicant_name', request.user.full_name)
                applicant_phone = request.POST.get('applicant_phone', request.user.phone)
                
                # Check if they already applied or are assigned
                app = EventApplication.objects.filter(booking=booking, staff=request.user).first()
                if app:
                    if app.status == 'cancelled':
                        messages.error(request, "You already cancelled this booking. Please contact Admin.")
                    else:
                        messages.info(request, "You have already applied for this event.")
                elif request.user in booking.assigned_to.all():
                    messages.info(request, "You are already assigned to this event.")
                else:
                    # If direct join BUT it's a double-work situation, force pending for admin review
                    if booking.allow_direct_join and not is_double_work_post:
                        EventApplication.objects.create(
                            booking=booking,
                            staff=request.user,
                            applicant_name=applicant_name,
                            applicant_phone=applicant_phone,
                            note=request.POST.get('note', ''),
                            status='approved',
                            is_double_work=False
                        )
                        booking.assigned_to.add(request.user)
                        messages.success(request, f'✅ Success! You have joined {booking.name}.')
                        # Notify admin in background (non-blocking)
                        threading.Thread(target=notify_admins, kwargs={
                            'title': '✅ Staff Joined Event',
                            'body': f"{request.user.full_name} directly joined {booking.name} on {booking.event_date}.",
                            'link': f"/admin-panel/bookings/{booking.pk}/"
                        }, daemon=True).start()
                    else:
                        # Either non-direct-join OR double-work situation — goes for admin review
                        EventApplication.objects.create(
                            booking=booking,
                            staff=request.user,
                            applicant_name=applicant_name,
                            applicant_phone=applicant_phone,
                            note=request.POST.get('note', ''),
                            status='pending',
                            is_double_work=is_double_work_post
                        )
                        if is_double_work_post:
                            messages.success(request, f'⚠️ Double Work Detected! Your application for {booking.name} has been sent to Admin for review.')
                            threading.Thread(target=notify_admins, kwargs={
                                'title': '⚠️ Double Work Application',
                                'body': f"{request.user.full_name} has applied for {booking.name} on {booking.event_date} but already has another booking that day. Admin review required.",
                                'link': '/admin-panel/staff-requests/'
                            }, daemon=True).start()
                        else:
                            messages.success(request, f'📩 Application received for {booking.name}. Check your dashboard for updates.')
                            threading.Thread(target=notify_admins, kwargs={
                                'title': '📩 New Event Application',
                                'body': f"{request.user.full_name} applied for {booking.name} on {booking.event_date}.",
                                'link': f"/admin-panel/bookings/{booking.pk}/"
                            }, daemon=True).start()
                
                
                
                return redirect('staff_dashboard')
                
        except Exception as e:
            # Catch potential IntegrityError or other DB issues
            messages.error(request, f"❌ Error: Could not process application. ({str(e)})")
            return redirect('staff_dashboard')
            
        return redirect('staff_dashboard')



@login_required(login_url='/staff/login/')
def staff_cancel_request(request, pk):
    """Files a cancellation request or withdraws a pending application."""
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)

        # 0. Guard: cannot cancel a booking that is already completed or cancelled
        if booking.status in ['completed', 'cancelled']:
            messages.error(request, "This event is already closed and cannot be cancelled.")
            return redirect('staff_dashboard')
        
        # 1. Check if cancellation is allowed (24h rule)
        if not booking.is_cancellable:
            messages.error(request, "Cancellation is no longer allowed as the event is less than 24 hours away.")
            return redirect('staff_dashboard')
            
        from bookings.models import EventApplication
        application = EventApplication.objects.filter(booking=booking, staff=request.user).first()
        
        if not application:
            if request.user in booking.assigned_to.all():
                # Staff was manually assigned by Admin without a pending app
                application = EventApplication.objects.create(
                    booking=booking,
                    staff=request.user,
                    applicant_name=request.user.full_name,
                    applicant_phone=request.user.phone,
                    status='cancel_requested'
                )
                messages.success(request, "Cancellation requested. The Admin must approve your request.")
            else:
                messages.error(request, "You do not have an active application for this event.")
            return redirect('staff_dashboard')

        # 2. Process based on current status
        if application.status in ['cancelled', 'cancel_requested']:
            messages.error(request, "You have already cancelled or requested cancellation for this event.")
        elif application.status == 'pending':
            # Instant withdrawal for pending applications
            application.status = 'cancelled'
            application.save()
            from django.core.cache import cache
            cache.delete(f'staff_dash_stats_v2_{request.user.pk}')
            messages.success(request, "Your application has been withdrawn.")
        elif application.status == 'approved':
            # Approved apps must go through Admin approval
            # Reset cancel_rejected flag if admin had previously denied a cancel request
            if application.cancel_rejected:
                application.cancel_rejected = False
            application.status = 'cancel_requested'
            application.save()
            from django.core.cache import cache
            cache.delete(f'staff_dash_stats_v2_{request.user.pk}')
            messages.success(request, "Cancellation requested. The Admin must approve your request.")
            # Notify admin again
            notify_admins(
                title="⚠️ Cancel Request",
                body=f"{request.user.full_name} has requested to cancel their slot for {booking.name} on {booking.event_date}.",
                link=f"/admin-panel/staff-requests/"
            )
        else:
            messages.error(request, "You cannot cancel this application in its current state.")
            
    
    
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

@login_required(login_url='/staff/login/')
def staff_profile(request):
    """Displays the staff member's profile and handles profile photo upload/removal."""
    me = request.user

    if request.method == 'POST':
        # Handle photo removal
        if request.POST.get('remove_photo') == '1':
            if me.photo:
                import os
                old_path = me.photo.path
                if os.path.isfile(old_path):
                    os.remove(old_path)
                me.photo = None
                me.save(update_fields=['photo'])
                messages.success(request, 'Profile photo removed.')

        # Handle photo upload
        elif 'photo' in request.FILES:
            photo = request.FILES['photo']
            if photo.size > 2 * 1024 * 1024:
                messages.error(request, '📷 Photo too large — maximum size is 2 MB.')
            elif photo.content_type not in ('image/jpeg', 'image/jpg', 'image/png', 'image/webp'):
                messages.error(request, '📷 Invalid file type — only JPEG, PNG, or WebP allowed.')
            else:
                # Delete old photo from disk if exists
                if me.photo:
                    import os
                    old_path = me.photo.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                me.photo = photo
                me.save(update_fields=['photo'])
                messages.success(request, '✅ Profile photo updated successfully.')

    # Context for Level Progress Tracking
    today = timezone.now().date()
    my_bookings = me.bookings.all()

    # Reuse dashboard cache to avoid 3 extra COUNT queries on every profile load
    _dash_cache = cache.get(f'staff_dash_stats_v2_{me.pk}')
    if _dash_cache and 'day_works' in _dash_cache:
        day_works   = _dash_cache['day_works']
        night_works = _dash_cache['night_works']
        long_works  = _dash_cache['long_works']
    else:
        day_works   = my_bookings.filter(status='completed', session='day').count()
        night_works = my_bookings.filter(status='completed', session='night').count()
        long_works  = my_bookings.filter(status='completed', is_long_work=True).count()

    rem_day, rem_night, rem_long = 0, 0, 0
    if me.level == 'C':
        rem_day   = max(0, 10 - day_works)
        rem_night = max(0, 5  - night_works)
        rem_long  = max(0, 5  - long_works)

    latest_promotion = me.promotion_requests.order_by('-created_at').first()

    return render(request, 'staff/profile.html', {
        'me': me,
        'day_works': day_works,
        'night_works': night_works,
        'long_works': long_works,
        'rem_day': rem_day,
        'rem_night': rem_night,
        'rem_long': rem_long,
        'latest_promotion': latest_promotion,
    })


@login_required(login_url='/staff/login/')
def upload_profile_photo(request):
    """AJAX endpoint: receives base64-encoded cropped image from Cropper.js, saves as profile photo."""
    from django.http import JsonResponse
    import base64
    import os
    from django.core.files.base import ContentFile

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    data_url = request.POST.get('cropped_image', '')
    if not data_url or not data_url.startswith('data:image/'):
        return JsonResponse({'success': False, 'error': 'No valid image data received.'}, status=400)

    try:
        # Parse "data:image/jpeg;base64,<DATA>"
        header, encoded = data_url.split(',', 1)
        # Determine extension
        mime = header.split(';')[0].split(':')[1]  # e.g. image/jpeg
        ext_map = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
        ext = ext_map.get(mime, 'jpg')

        image_data = base64.b64decode(encoded)

        # Size check: max 3 MB after decode
        if len(image_data) > 3 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'Cropped image too large (max 3 MB).'}, status=400)

        me = request.user

        # Delete old photo file from disk
        if me.photo:
            old_path = me.photo.path
            if os.path.isfile(old_path):
                os.remove(old_path)

        filename = f"profile_{me.staff_id}.{ext}"
        me.photo.save(filename, ContentFile(image_data), save=True)

        return JsonResponse({'success': True, 'photo_url': me.photo.url})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/staff/login/')
def staff_terms(request):
    """Displays the terms and conditions for staff members."""
    from core.models import TermAndCondition
    terms = TermAndCondition.objects.all()
    return render(request, 'staff/terms.html', {'terms': terms})


@login_required(login_url='/staff/login/')
def staff_submit_report(request, pk):
    """Allows assigned Captains to submit or update settlement reports for an event directly to admin."""
    from bookings.models import EventReport
    me = request.user
    
    booking = get_object_or_404(Booking, pk=pk)
    
    if not booking.assigned_to.filter(id=me.id).exists() and not me.is_staff:
        messages.error(request, 'You do not have access to this booking.')
        return redirect('staff_dashboard')
        
    existing_report = EventReport.objects.filter(booking=booking).first()

    if request.method == 'POST':
        try:
            if existing_report and existing_report.status == 'submitted':
                messages.error(request, 'This report has already been finalized and cannot be modified.')
                if request.GET.get('from') == 'admin':
                    return redirect('admin_event_report_detail', pk=existing_report.pk)
                return redirect('staff_booking_detail', pk=pk)

            action = request.POST.get('action', 'draft')

            if existing_report:
                report = existing_report
            else:
                report = EventReport(booking=booking, submitted_by=me)
                
            report.status = 'submitted' if action == 'submit' else 'draft'
            report.bill_in_charge = request.POST.get('bill_in_charge', 'NIL').strip() or 'NIL'
            report.total_amount   = request.POST.get('total_amount', 'NIL').strip() or 'NIL'
            report.balance_amount = request.POST.get('balance_amount', 'NIL').strip() or 'NIL'
            report.pending        = request.POST.get('pending', 'NIL').strip() or 'NIL'
            report.work_type      = request.POST.get('work_type', 'day')
            report.juice          = request.POST.get('juice', 'NIL').strip() or 'NIL'
            report.tea            = request.POST.get('tea', 'NIL').strip() or 'NIL'
            report.popcorn        = request.POST.get('popcorn', 'NIL').strip() or 'NIL'
            report.hosting        = request.POST.get('hosting', 'NIL').strip() or 'NIL'
            report.coat_incharge  = request.POST.get('coat_incharge', 'NIL').strip() or 'NIL'
            report.coat_rent      = request.POST.get('coat_rent', 'NIL').strip() or 'NIL'
            report.ta             = request.POST.get('ta', 'NIL').strip() or 'NIL'
            report.plate_count    = request.POST.get('plate_count', 'NIL').strip() or 'NIL'
            report.bottle_count   = request.POST.get('bottle_count', 'NIL').strip() or 'NIL'
            report.extra_logistics = request.POST.get('extra_logistics', 'NIL').strip() or 'NIL'
            
            # Dynamic Logistics
            log_labels = request.POST.getlist('dyn_log_label[]')
            log_vals   = request.POST.getlist('dyn_log_val[]')
            report.dynamic_logistics = {l.strip(): v.strip() or 'NIL' for l, v in zip(log_labels, log_vals) if l.strip()}
            
            # Dynamic Rentals
            rent_labels = request.POST.getlist('dyn_rent_label[]')
            rent_vals   = request.POST.getlist('dyn_rent_val[]')
            report.dynamic_rentals = {l.strip(): v.strip() or 'NIL' for l, v in zip(rent_labels, rent_vals) if l.strip()}

            report.note           = request.POST.get('note', '').strip()
            report.save()
            
            messages.success(request, 'Report updated/submitted successfully.')
            if request.GET.get('from') == 'admin':
                return redirect('admin_event_report_detail', pk=report.pk)
            return redirect('staff_booking_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'Error submitting report: {e}')
    
    assigned_count = booking.assigned_to.count()
    is_admin = request.GET.get('from') == 'admin'
    base_template = 'admin/custom_base.html' if is_admin else 'staff/base.html'
    
    return render(request, 'staff/submit_report.html', {
        'booking': booking,
        'assigned_count': assigned_count,
        'report': existing_report,
        'base_template': base_template,
        'is_admin': is_admin
    })

@login_required(login_url='/staff/login/')
def staff_complete_task(request, pk):
    """AJAX endpoint to mark a Captain task as completed."""
    from bookings.models import EventTask
    from django.utils import timezone
    from django.http import JsonResponse
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'})
        
    task_id = request.POST.get('task_id')
    if not task_id:
        return JsonResponse({'success': False, 'error': 'No task ID provided'})
        
    me = request.user
    task = get_object_or_404(EventTask, id=task_id, booking__id=pk)
    
    # Check if they are assigned to booking
    if not task.booking.assigned_to.filter(id=me.id).exists() and not me.is_staff:
        return JsonResponse({'success': False, 'error': 'Unauthorized'})
        
    if not task.is_completed:
        task.is_completed = True
        task.completed_by = me
        task.completed_at = timezone.now()
        task.save()
        
    return JsonResponse({
        'success': True,
        'task_name': task.task_name,
        'completed_by': task.completed_by.full_name if task.completed_by else 'Unknown'
    })


@login_required(login_url='/staff/login/')
@require_POST
def staff_ajax_update_attendance_field(request, pk):
    """AJAX endpoint for Captains/Supervisors to update attendance fields."""
    me = request.user
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check: Must be admin or high-level staff assigned to this booking
    is_assigned = booking.assigned_to.filter(id=me.id).exists()
    has_perm = me.is_staff or (is_assigned and me.level in ['captain', 'supervisor'])
    
    if not has_perm:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

    staff_id = request.POST.get('staff_id')
    field    = request.POST.get('field')
    value    = request.POST.get('value')

    if not all([staff_id, field]):
        return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

    try:
        from staff.models import StaffAttendance, Staff
        att, created = StaffAttendance.objects.get_or_create(
            booking=booking,
            staff_id=staff_id,
            date=booking.event_date
        )

        from decimal import Decimal
        if field == 'status':
            att.status = value.strip().lower()
        elif field == 'payment_given':
            att.payment_given = (value == 'true')
        elif field == 'bonus':
            att.bonus = Decimal(str(value or 0))
        elif field == 'deduction':
            att.deduction = Decimal(str(value or 0))
        elif field == 'reaching_time':
            att.reaching_time = value if value and value != 'None' else None
        elif field in ['on_time', 'shoes', 'uniform', 'grooming']:
            setattr(att, field, (value == 'true'))
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid field'}, status=400)

        att.save()

        # Send push if status changed to Present
        if field == 'status' and value == 'present':
            try:
                from core.utils import send_push_notification
                staff_member = att.staff
                title = "Attendance Marked ✅"
                msg = f"Your attendance for {booking.name} has been marked as Present by {me.full_name}."
                send_push_notification(staff_member, title, msg)
            except Exception as e:
                print(f"Staff Push Error: {e}")

        return JsonResponse({
            'status': 'success', 
            'message': 'Updated successfully'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def staff_apply(request):
    """In-app registration for new staff members, skipping the main website."""
    from staff.forms import StaffApplicationForm
    if request.user.is_authenticated:
        return redirect('staff_dashboard')
        
    error = None
    if request.method == 'POST':
        form = StaffApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                application = form.save(commit=False)
                application.status = 'pending'
                application.save()
                messages.success(request, '🎉 Application submitted successfully! An Admin will review the application and WhatsApp you the login details shortly.')
                return redirect('staff_login')
            except Exception as e:
                error = 'Something went wrong processing your staff application. Please try again.'
        else:
            error = 'Please correct the errors below.'
    else:
        form = StaffApplicationForm()
        
    from staff.models import Locality
    return render(request, 'staff/apply.html', {
        'form': form, 
        'error': error,
        'localities': Locality.objects.all().order_by('name'),
    })

