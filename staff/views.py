from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
import json

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.db.models import Sum, Count, Q
from django.db import transaction
from django.core.cache import cache

from .models import Staff, StaffPayout, StaffAttendance, StaffNotice, FCMDevice
from bookings.models import Booking, BookingPayment, EventApplication
from core.utils import notify_admins



from django.views.decorators.csrf import csrf_exempt

# ── Firebase ────────────────────────────────────────────────────────────────
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
    from django.utils import timezone
    from core.pdf_utils import build_attendance_pdf

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
        cache.set(cache_key, cached_stats, 60) # 1 minute cache for fast reaction
        
    # Calculate Published Bookings Quota dynamic availability (already optimized with prefetch)
    available_bookings_qs = Booking.objects.filter(
        status__in=['pending', 'confirmed'], 
        event_date__gte=today,
        is_published=True
    ).exclude(assigned_to=me).prefetch_related('applications__staff').order_by('event_date')
    
    available_bookings = []
    for b in available_bookings_qs:
        # Locality filter
        if b.publish_locality != 'all' and me.main_locality != b.publish_locality:
            continue
            
        if len(available_bookings) >= 20:
            break
            
        # Use Python list comprehension to use prefetched data and avoid N+1 DB hit
        approved_count = len([app for app in b.applications.all() if app.status == 'approved' and app.staff.level == me.level])
        
        is_full = False
        if me.level == 'captain' and b.quota_captain > 0 and approved_count >= b.quota_captain:
            is_full = True
        elif me.level == 'A' and b.quota_a > 0 and approved_count >= b.quota_a:
            is_full = True
        elif me.level == 'B' and b.quota_b > 0 and approved_count >= b.quota_b:
            is_full = True
        elif me.level == 'C' and b.quota_c > 0 and approved_count >= b.quota_c:
            is_full = True
            
        b.is_level_full = is_full
        available_bookings.append(b)

    rem_day, rem_night, rem_long = 0, 0, 0
    if me.level == 'C':
        rem_day = max(0, 10 - cached_stats.get('day_works', 0))
        rem_night = max(0, 5 - cached_stats.get('night_works', 0))
        rem_long = max(0, 5 - cached_stats.get('long_works', 0))

    latest_promotion = me.promotion_requests.order_by('-created_at').first()
    active_notice = StaffNotice.objects.filter(is_active=True).first()

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
        if me.level != 'captain' and not me.is_staff:
            messages.error(request, 'Only Captains can mark attendance.')
            return redirect('staff_booking_detail', pk=pk)
            
        staff_ids = request.POST.getlist('staff_ids[]')
        date_str = request.POST.get('attendance_date', booking.event_date.strftime('%Y-%m-%d'))
        
        with transaction.atomic():
            for sid in staff_ids:
                status = request.POST.get(f'attendance_status_{sid}', 'present')
                reaching_time_str = request.POST.get(f'reaching_time_{sid}')
                
                on_time = request.POST.get(f'on_time_{sid}') == 'on'
                shoes = request.POST.get(f'shoes_{sid}') == 'on'
                uniform = request.POST.get(f'uniform_{sid}') == 'on'
                grooming = request.POST.get(f'grooming_{sid}') == 'on'
                payment_given = request.POST.get(f'payment_given_{sid}') == 'on'
                
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
                        'on_time': on_time,
                        'shoes': shoes,
                        'uniform': uniform,
                        'grooming': grooming,
                        'payment_given': payment_given
                    }
                )
        messages.success(request, f'Attendance marked for {len(staff_ids)} staff members.')
        return redirect('staff_booking_detail', pk=pk)

    assigned_staff_list = []
    attendances = StaffAttendance.objects.filter(booking=booking, date=booking.event_date)
    att_map = {a.staff_id: a for a in attendances}
    applications_map = {app.staff_id: app for app in booking.applications.filter(status__in=['approved', 'pending'])}
    
    for s in booking.assigned_to.all():
        app = applications_map.get(s.id)
        phone = app.applicant_phone if app and app.applicant_phone else s.phone
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

    # If GET, render a simple apply form
    if request.method == 'GET':
        return render(request, 'staff/apply_booking.html', {'booking': booking, 'user': request.user})
    
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
                    messages.error(request, f"⚠️ Collision: You already have a {booking.get_session_display()} shift on {booking.event_date.strftime('%d %b')}.")
                    return redirect('staff_dashboard')
                # -----------------------------------
                
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
                    if booking.allow_direct_join:
                        EventApplication.objects.create(
                            booking=booking,
                            staff=request.user,
                            applicant_name=applicant_name,
                            applicant_phone=applicant_phone,
                            note=request.POST.get('note', ''),
                            status='approved'
                        )
                        booking.assigned_to.add(request.user)
                        messages.success(request, f'✅ Success! You have joined {booking.name}.')
                        # Notify admin about direct join
                        notify_admins(
                            title="✅ Staff Joined Event",
                            body=f"{request.user.full_name} directly joined {booking.name} on {booking.event_date}.",
                            link=f"/admin-panel/bookings/{booking.pk}/"
                        )
                    else:
                        EventApplication.objects.create(
                            booking=booking,
                            staff=request.user,
                            applicant_name=applicant_name,
                            applicant_phone=applicant_phone,
                            note=request.POST.get('note', ''),
                            status='pending'
                        )
                        messages.success(request, f'📩 Application received for {booking.name}. Check your dashboard for updates.')
                        # Notify admin about new application
                        notify_admins(
                            title="📩 New Event Application",
                            body=f"{request.user.full_name} applied for {booking.name} on {booking.event_date}.",
                            link=f"/admin-panel/bookings/{booking.pk}/"
                        )
                
                
                
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
            messages.error(request, "You do not have an active application for this event.")
            return redirect('staff_dashboard')

        # 2. Process based on current status
        if application.status in ['cancelled', 'cancel_requested']:
            messages.error(request, "You have already cancelled or requested cancellation for this event.")
        elif application.status == 'pending':
            # Instant withdrawal for pending applications
            application.status = 'cancelled'
            application.save()
            messages.success(request, "Your application has been withdrawn.")
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

    return render(request, 'staff/profile.html', {'me': me})


@login_required(login_url='/staff/login/')
def upload_profile_photo(request):
    """AJAX endpoint: receives base64-encoded cropped image from Cropper.js, saves as profile photo."""
    from django.http import JsonResponse
    import base64, io, os
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
    return render(request, 'staff/terms.html')


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
            report.juice          = request.POST.get('juice', 'NIL').strip() or 'NIL'
            report.tea            = request.POST.get('tea', 'NIL').strip() or 'NIL'
            report.popcorn        = request.POST.get('popcorn', 'NIL').strip() or 'NIL'
            report.hosting        = request.POST.get('hosting', 'NIL').strip() or 'NIL'
            report.coat_incharge  = request.POST.get('coat_incharge', 'NIL').strip() or 'NIL'
            report.coat_rent      = request.POST.get('coat_rent', 'NIL').strip() or 'NIL'
            report.ta             = request.POST.get('ta', 'NIL').strip() or 'NIL'
            report.save()
            
            messages.success(request, 'Report updated/submitted successfully.')
            if request.GET.get('from') == 'admin':
                return redirect('admin_event_report_detail', pk=report.pk)
            return redirect('staff_booking_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'Error submitting report: {e}')
    
    assigned_count = booking.assigned_to.count()
    return render(request, 'staff/submit_report.html', {
        'booking': booking,
        'assigned_count': assigned_count,
        'report': existing_report
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

