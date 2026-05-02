from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin-panel/login/')(view_func)
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
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
            # Make session permanent (1 year)
            request.session.set_expiry(60 * 60 * 24 * 365)
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
            # Assign staff & Dynamic Quota Adjustment
            old_assigned_ids = set(booking.assigned_to.values_list('id', flat=True))
            new_assigned_ids = set(map(int, request.POST.getlist('assigned_to')))
            
            added_ids = new_assigned_ids - old_assigned_ids
            removed_ids = old_assigned_ids - new_assigned_ids
            
            quota_changed = False
            if added_ids:
                added_staff = Staff.objects.filter(id__in=added_ids)
                for s in added_staff:
                    role_key = s.level
                    if role_key == 'supervisor':
                        filled = booking.assigned_to.filter(level='supervisor').count() + 1
                        if (booking.quota_supervisor or 0) < filled: booking.quota_supervisor = filled
                    elif role_key == 'captain':
                        filled = booking.assigned_to.filter(level='captain').count() + 1
                        if (booking.quota_captain or 0) < filled: booking.quota_captain = filled
                    elif role_key == 'A':
                        filled = booking.assigned_to.filter(level='A').count() + 1
                        if (booking.quota_a or 0) < filled: booking.quota_a = filled
                    elif role_key == 'B':
                        filled = booking.assigned_to.filter(level='B').count() + 1
                        if (booking.quota_b or 0) < filled: booking.quota_b = filled
                    elif role_key == 'C':
                        filled = booking.assigned_to.filter(level='C').count() + 1
                        if (booking.quota_c or 0) < filled: booking.quota_c = filled
                quota_changed = True
            
            if removed_ids:
                removed_staff = Staff.objects.filter(id__in=removed_ids)
                for s in removed_staff:
                    if s.level == 'captain': booking.quota_captain = max(0, (booking.quota_captain or 0) - 1)
                    elif s.level == 'supervisor': booking.quota_supervisor = max(0, (booking.quota_supervisor or 0) - 1)
                    elif s.level == 'A': booking.quota_a = max(0, (booking.quota_a or 0) - 1)
                    elif s.level == 'B': booking.quota_b = max(0, (booking.quota_b or 0) - 1)
                    elif s.level == 'C': booking.quota_c = max(0, (booking.quota_c or 0) - 1)
                quota_changed = True
            
            if quota_changed:
                booking.save(update_fields=['quota_captain', 'quota_supervisor', 'quota_a', 'quota_b', 'quota_c'])
                
            booking.assigned_to.set(new_assigned_ids)
            
            # Recalculate work counts for ALL affected staff (new and old)
            affected_staff_ids = old_assigned_ids | new_assigned_ids
            # If status changed to/from 'completed', or if staff list changed on a 'completed' event
            if (old_status == 'completed' or booking.status == 'completed') or (booking.status == 'completed' and (added_ids or removed_ids)):
                for staff_id in affected_staff_ids:
                    s = Staff.objects.get(id=staff_id)
                    s.total_events_completed = s.bookings.filter(status='completed').count()
                    s.save(update_fields=['total_events_completed'])
                    
                    # Promotion check for Level-C
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
            EventApplication.objects.filter(booking=booking, staff_id__in=new_assigned_ids, status='pending').update(status='approved')
            # If manually removed from event:
            # 1. Cancel any cancel_requested apps for removed staff
            EventApplication.objects.filter(booking=booking, status='cancel_requested').exclude(staff_id__in=new_assigned_ids).update(status='cancelled')
            # 2. Also cancel any APPROVED apps for staff who were manually removed — this is the key fix
            #    so their dashboard no longer shows the Join/Apply button
            if removed_ids:
                EventApplication.objects.filter(
                    booking=booking,
                    staff_id__in=removed_ids,
                    status='approved'
                ).update(status='cancelled')
            
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
            # Attendance is now handled via AJAX. 
            # Keeping this block empty to prevent errors if a legacy POST occurs.
            pass

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
    filled_counts = {'supervisor': 0, 'captain': 0, 'A': 0, 'B': 0, 'C': 0}
    total_quota = (booking.quota_supervisor or 0) + (booking.quota_captain or 0) + \
                  (booking.quota_a or 0) + (booking.quota_b or 0) + (booking.quota_c or 0)
    total_filled = 0

    for s in booking.assigned_to.all():
        if s.level not in ['captain', 'supervisor']:
            if s.coat_size and s.coat_size in coat_counts:
                coat_counts[s.coat_size] += 1
        
        # Calculate filled counts by level
        if s.level == 'supervisor': 
            filled_counts['supervisor'] += 1
            total_filled += 1
        elif s.level == 'captain': 
            filled_counts['captain'] += 1
            total_filled += 1
        elif s.level == 'A': 
            filled_counts['A'] += 1
            total_filled += 1
        elif s.level == 'B': 
            filled_counts['B'] += 1
            total_filled += 1
        elif s.level == 'C': 
            filled_counts['C'] += 1
            total_filled += 1

        phone = s.phone
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
        'total_quota': total_quota,
        'total_filled': len(assigned_staff_with_att),
        'attendance_map': attendance_map,
        'assigned_staff_with_att': assigned_staff_with_att,
        'payments': payments,
        'pending_applications': pending_applications,
        'cancel_requests': cancel_requests,
        'today': timezone.now().date(),
        'page': 'bookings',
        'captain_tasks': booking.tasks.all().order_by('id'),
        'localities': __import__('staff').models.Locality.objects.all(),
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
def admin_quick_update_quota(request, pk):
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
    
    booking = get_object_or_404(Booking, pk=pk)
    role = request.POST.get('role')
    delta = request.POST.get('delta') # +1 or -1
    
    if not role or delta is None:
        return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)
    
    try:
        d = int(delta)
        
        # Current DB value
        if role == 'captain':
            current_quota = booking.quota_captain
            filled = booking.assigned_to.filter(level='captain').count()
        elif role == 'supervisor':
            current_quota = booking.quota_supervisor
            filled = booking.assigned_to.filter(level='supervisor').count()
        elif role in ['a', 'b', 'c']:
            current_quota = getattr(booking, f'quota_{role}')
            filled = booking.assigned_to.filter(level=role.upper()).count()
        else: 
            return JsonResponse({'status': 'error', 'message': 'Invalid role'}, status=400)
            
        new_val = current_quota + d
        
        # Floor check
        if d < 0 and new_val < filled:
            return JsonResponse({
                'status': 'error', 
                'message': f'Cannot decrease {role.upper()} quota below {filled} (currently assigned).'
            }, status=400)
        
        if d > 0 and new_val < filled + 1:
            new_val = filled + 1
            
        if role == 'captain': booking.quota_captain = new_val
        elif role == 'supervisor': booking.quota_supervisor = new_val
        else: setattr(booking, f'quota_{role}', new_val)
        
        update_field = f'quota_{role}' if role != 'captain' else 'quota_captain'
        booking.save(update_fields=[update_field])
        
        total = (booking.quota_captain or 0) + (booking.quota_supervisor or 0) + \
                (booking.quota_a or 0) + (booking.quota_b or 0) + (booking.quota_c or 0)
        return JsonResponse({'status': 'success', 'new_val': new_val, 'total': total})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@admin_required
@require_POST
def admin_ajax_update_booking_field(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    field_name = request.POST.get('field')
    value = request.POST.get('value')
    
    allowed_fields = [
        'status', 'quoted_price', 'admin_notes', 
        'dietary_requirements', 'message', 'venue', 
        'event_time', 'budget', 'guest_count', 'assigned_to'
    ]
    
    if field_name not in allowed_fields:
        return JsonResponse({'status': 'error', 'message': f'Field {field_name} not allowed'}, status=400)
    
    try:
        msg = "Updated successfully"
        if field_name == 'quoted_price':
            setattr(booking, field_name, float(value) if value else None)
        elif field_name in ['budget', 'guest_count']:
            setattr(booking, field_name, int(value) if value else 0)
        elif field_name == 'assigned_to':
            sub_action = request.POST.get('sub_action', 'add')
            staff_id = value
            if staff_id:
                try:
                    from bookings.models import EventApplication
                    s = Staff.objects.get(id=staff_id)
                    if sub_action == 'add':
                        booking.assigned_to.add(s)
                        msg = f"Added {s.full_name} to event!"
                        
                        # Auto-adjust quota if it's exceeded
                        role_key = s.level
                        if role_key == 'supervisor':
                            filled = booking.assigned_to.filter(level='supervisor').count()
                            if (booking.quota_supervisor or 0) < filled: booking.quota_supervisor = filled
                        elif role_key == 'captain':
                            filled = booking.assigned_to.filter(level='captain').count()
                            if (booking.quota_captain or 0) < filled: booking.quota_captain = filled
                        elif role_key == 'A':
                            filled = booking.assigned_to.filter(level='A').count()
                            if (booking.quota_a or 0) < filled: booking.quota_a = filled
                        elif role_key == 'B':
                            filled = booking.assigned_to.filter(level='B').count()
                            if (booking.quota_b or 0) < filled: booking.quota_b = filled
                        elif role_key == 'C':
                            filled = booking.assigned_to.filter(level='C').count()
                            if (booking.quota_c or 0) < filled: booking.quota_c = filled
                        
                        booking.save(update_fields=['quota_captain', 'quota_supervisor', 'quota_a', 'quota_b', 'quota_c'])
                        
                        # Mark pending apps as approved
                        EventApplication.objects.filter(booking=booking, staff=s, status='pending').update(status='approved')
                        
                    else:
                        booking.assigned_to.remove(s)
                        msg = f"Removed {s.full_name} from event"
                        
                        # Auto-decrease quota
                        if s.level == 'captain': booking.quota_captain = max(0, (booking.quota_captain or 0) - 1)
                        elif s.level == 'supervisor': booking.quota_supervisor = max(0, (booking.quota_supervisor or 0) - 1)
                        elif s.level == 'A': booking.quota_a = max(0, (booking.quota_a or 0) - 1)
                        elif s.level == 'B': booking.quota_b = max(0, (booking.quota_b or 0) - 1)
                        elif s.level == 'C': booking.quota_c = max(0, (booking.quota_c or 0) - 1)
                        
                        booking.save(update_fields=['quota_captain', 'quota_supervisor', 'quota_a', 'quota_b', 'quota_c'])
                        
                        # Mark cancel requests as cancelled
                        EventApplication.objects.filter(booking=booking, staff=s, status='cancel_requested').update(status='cancelled')
                        
                except Staff.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': 'Staff not found'}, status=404)
            else:
                return JsonResponse({'status': 'error', 'message': 'No staff ID provided'}, status=400)
        else:
            setattr(booking, field_name, value)
            
        if field_name == 'assigned_to':
            pass # Already saved through model relations and update_fields above
        else:
            booking.save(update_fields=[field_name])
            
        # Recalculate filled counts for response
        counts = {
            'supervisor': booking.assigned_to.filter(level='supervisor').count(),
            'captain': booking.assigned_to.filter(level='captain').count(),
            'a': booking.assigned_to.filter(level='A').count(),
            'b': booking.assigned_to.filter(level='B').count(),
            'c': booking.assigned_to.filter(level='C').count(),
        }
        total_filled = sum(counts.values())
        total_quota = (booking.quota_captain or 0) + (booking.quota_supervisor or 0) + \
                      (booking.quota_a or 0) + (booking.quota_b or 0) + (booking.quota_c or 0)
        
        return JsonResponse({
            'status': 'success', 
            'message': msg,
            'filled': counts, 
            'total_filled': total_filled, 
            'total_quota': total_quota
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@admin_required
@require_POST
def admin_ajax_update_attendance_field(request, pk):
    from staff.models import StaffAttendance
    booking = get_object_or_404(Booking, pk=pk)
    staff_id = request.POST.get('staff_id')
    field = request.POST.get('field')
    value = request.POST.get('value')

    if not staff_id or not field:
        print(f"Attendance Update Error: Missing staff_id or field. Received: staff_id={staff_id}, field={field}")
        return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

    print(f"Attendance Update: Booking {booking.pk}, Staff {staff_id}, Field {field}, Value {value}")

    try:
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
        print(f"Attendance Saved: {att}")

        # Real-time counts for ribbon
        from staff.models import StaffAttendance
        present_counts = {
            'supervisor': StaffAttendance.objects.filter(booking=booking, status='present', staff__level='supervisor').count(),
            'captain': StaffAttendance.objects.filter(booking=booking, status='present', staff__level='captain').count(),
            'A': StaffAttendance.objects.filter(booking=booking, status='present', staff__level='A').count(),
            'B': StaffAttendance.objects.filter(booking=booking, status='present', staff__level='B').count(),
            'C': StaffAttendance.objects.filter(booking=booking, status='present', staff__level='C').count(),
        }
        total_present = StaffAttendance.objects.filter(booking=booking, status='present').count()

        # Send push if status changed
        if field == 'status' and value in ['present', 'absent']:
            try:
                from core.utils import send_push_notification
                staff = att.staff
                title = "Attendance Updated"
                msg = f"Your attendance for {booking.name} has been marked as {value.capitalize()} ✅" if value == 'present' else f"Your attendance for {booking.name} has been marked as Absent ❌"
                send_push_notification(staff, title, msg)
            except Exception as e:
                print(f"Push Notification Error: {e}")

        return JsonResponse({
            'status': 'success', 
            'message': 'Attendance updated',
            'present_counts': {
                'supervisor': present_counts.get('supervisor', 0),
                'captain': present_counts.get('captain', 0),
                'a': present_counts.get('A', 0),
                'b': present_counts.get('B', 0),
                'c': present_counts.get('C', 0),
            },
            'total_present': total_present,
            'booking_id': booking.pk
        })
    except Exception as e:
        import traceback
        print(f"CRITICAL AJAX ERROR: {e}")
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
        # Count staff at each level from the assigned_to list (source of truth)
        assigned_staff = booking.assigned_to.all()
        counts = {
            'supervisor': len([s for s in assigned_staff if s.level == 'supervisor']),
            'captain': len([s for s in assigned_staff if s.level == 'captain']),
            'a': len([s for s in assigned_staff if s.level == 'A']),
            'b': len([s for s in assigned_staff if s.level == 'B']),
            'c': len([s for s in assigned_staff if s.level == 'C']),
        }

        quota_data = {
            'supervisor': {'q': booking.quota_supervisor, 'c': counts['supervisor']},
            'captain': {'q': booking.quota_captain, 'c': counts['captain']},
            'a': {'q': booking.quota_a, 'c': counts['a']},
            'b': {'q': booking.quota_b, 'c': counts['b']},
            'c': {'q': booking.quota_c, 'c': counts['c']},
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
            # Fix 4: Prevent past dates in new bookings
            from datetime import date as date_type
            event_date_str = request.POST.get('event_date', '')
            if event_date_str:
                try:
                    event_date_val = date_type.fromisoformat(event_date_str)
                    if event_date_val < date_type.today():
                        messages.error(request, 'Error: Past dates are not allowed for new bookings.')
                        return render(request, 'admin/create_booking.html', {'page': 'bookings'})
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
                guest_count = int(request.POST.get('guest_count')) if request.POST.get('guest_count') else None,
                budget      = request.POST.get('budget') or None,
                dietary_requirements = request.POST.get('dietary_requirements', ''),
                special_requests     = request.POST.get('special_requests', ''),
                message              = request.POST.get('message', ''),
                status               = 'confirmed',  # Manual admin entry defaults to confirmed
                # Note: quoted_price is NOT set from budget — set it separately in booking detail
                allow_direct_join    = request.POST.get('allow_direct_join') == 'on',
                is_long_work         = request.POST.get('is_long_work') == 'on',
                quota_captain        = int(request.POST.get('quota_captain') or 0),
                quota_supervisor     = int(request.POST.get('quota_supervisor') or 0),
                quota_a              = int(request.POST.get('quota_a') or 0),
                quota_b              = int(request.POST.get('quota_b') or 0),
                quota_c              = int(request.POST.get('quota_c') or 0),
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
            booking.guest_count = int(request.POST.get('guest_count')) if request.POST.get('guest_count') else None
            booking.budget = request.POST.get('budget') or None
            booking.dietary_requirements = request.POST.get('dietary_requirements', '')
            booking.message = request.POST.get('message', '')
            
            # Quotas & Locality
            # Floor check validation
            q_capt = int(request.POST.get('quota_captain') or 0)
            q_supr = int(request.POST.get('quota_supervisor') or 0)
            q_a = int(request.POST.get('quota_a') or 0)
            q_b = int(request.POST.get('quota_b') or 0)
            q_c = int(request.POST.get('quota_c') or 0)
            
            f_capt = booking.assigned_to.filter(level='captain').count()
            f_supr = booking.assigned_to.filter(level='supervisor').count()
            f_a = booking.assigned_to.filter(level='A').count()
            f_b = booking.assigned_to.filter(level='B').count()
            f_c = booking.assigned_to.filter(level='C').count()
            
            if q_capt < f_capt or q_supr < f_supr or q_a < f_a or q_b < f_b or q_c < f_c:
                messages.error(request, "Cannot set quota lower than currently assigned staff count.")
                return redirect('admin_edit_booking', pk=booking.pk)

            booking.quota_captain = q_capt
            booking.quota_supervisor = q_supr
            booking.quota_a = q_a
            booking.quota_b = q_b
            booking.quota_c = q_c
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
        'localities': __import__('staff').models.Locality.objects.all(),
    })


@admin_required
def admin_publish_booking(request, pk):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, pk=pk)
        action = request.POST.get('action', 'publish')
        
        if action == 'publish':
            if booking.status == 'pending':
                messages.error(request, "Cannot publish a pending event. Please update the event status to 'Confirmed' first.")
                return redirect('admin_booking_detail', pk=booking.pk)
                
            total_quota = (booking.quota_supervisor or 0) + (booking.quota_captain or 0) + (booking.quota_a or 0) + \
                          (booking.quota_b or 0) + (booking.quota_c or 0)
            if total_quota <= 0:
                messages.error(request, "Cannot publish event with zero quotas. Please set the required staff counts first.")
                return redirect('admin_booking_detail', pk=booking.pk)

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
            'supervisor': {'q': selected_booking_obj.quota_supervisor, 'c': selected_booking_obj.applications.filter(status='approved', staff__level='supervisor').count()},
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
    
    wa_url = request.session.pop('auto_whatsapp_url', None)
    wa_type = request.session.pop('auto_whatsapp_type', 'approve')
    
    context = {
        'applications': applications,
        'page': 'staff_applications',
        'auto_whatsapp_url': wa_url,
        'auto_whatsapp_type': wa_type,
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
            
            # WhatsApp Integration via Web Redirect
            import urllib.parse
            phone_raw = str(application.phone_1).replace('+', '').replace(' ', '').replace('-', '')
            if len(phone_raw) == 10:
                phone_raw = '91' + phone_raw
                
            # Emojis fixed via proper Unicode escapes. Using real domain for clickable links.
            login_url = "https://mastan.in/staff/login/"
            
            msg = (
                f"\U0001F389 *Welcome to Mastan Catering!*\n\n"
                f"Hi {application.full_name}, your staff registration has been approved. You can now login to the Staff Portal and start booking events.\n\n"
                f"\U0001F464 *Staff ID:* {new_id}\n"
                f"\U0001F511 *Password:* password123\n\n"
                f"\U0001F517 *Login Here:* {login_url}\n\n"
                f"_Note: You will be asked to securely change this password on your first login._"
            )
            
            wa_link = f"https://wa.me/{phone_raw}?text={urllib.parse.quote(msg)}"
            request.session['auto_whatsapp_url'] = wa_link
            request.session['auto_whatsapp_type'] = 'approve'
            
            messages.success(request, f'✅ Staff created! ID: {new_id} | Default Password: password123')
        except Exception as e:
            messages.error(request, f'Error creating staff: {str(e)}')
    elif action == 'reject':
        application.status = 'rejected'
        application.save()
        
        # WhatsApp Rejection Message
        import urllib.parse
        phone_raw = str(application.phone_1).replace('+', '').replace(' ', '').replace('-', '')
        if len(phone_raw) == 10:
            phone_raw = '91' + phone_raw
            
        msg = (
            f"Greetings from Mastan Catering. We regret to inform you that your registration application for the staff portal has been rejected.\n\n"
            f"If you have any questions, please contact our support team."
        )
        wa_link = f"https://wa.me/{phone_raw}?text={urllib.parse.quote(msg)}"
        request.session['auto_whatsapp_url'] = wa_link
        request.session['auto_whatsapp_type'] = 'reject'
        
        messages.success(request, 'Application rejected. You can notify the applicant via WhatsApp.')
        
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

    from staff.models import Locality
    context = {
        'staff': page_obj,
        'page': 'staff',
        'total_events_served': total_events_served,
        'total_staff_count': total_staff_count,
        'localities': Locality.objects.all(),
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
            from staff.models import Locality
            return render(request, 'admin/staff_add.html', {'page': 'staff', 'form_data': request.POST, 'localities': Locality.objects.all()})

        phone_2 = validate_phone(phone_2_raw) or phone_2_raw  # Alt phone is optional
        guardian_phone = validate_phone(guardian_phone_raw)
        if guardian_phone_raw and not guardian_phone:
            messages.error(request, f'Invalid guardian phone: "{guardian_phone_raw}". Please enter a valid 10-digit number.')
            from staff.models import Locality
            return render(request, 'admin/staff_add.html', {'page': 'staff', 'form_data': request.POST, 'localities': Locality.objects.all()})

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
            from staff.models import Locality
            return render(request, 'admin/staff_add.html', {
                'page': 'staff',
                'form_data': request.POST,
                'localities': Locality.objects.all()
            })

    from staff.models import Locality
    try:
        localities = Locality.objects.all()
    except Exception:
        localities = []
    
    return render(request, 'admin/staff_add.html', {'page': 'staff', 'localities': localities})


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

    from staff.models import Locality
    localities = Locality.objects.all()
    return render(request, 'admin/staff_edit.html', {'member': member, 'page': 'staff', 'localities': localities})



@admin_required
def staff_detail(request, pk):
    member = get_object_or_404(Staff.objects.prefetch_related('bookings', 'payouts'), pk=pk)
    today  = timezone.now().date()

    # Performance Fix 7: Optimization for staff_detail (limit and prefetch already handled by related_name queries)
    bookings   = member.bookings.all().order_by('-event_date')[:10]
    payouts    = member.payouts.all().order_by('-created_at')
    revenue    = member.total_revenue_generated()
    total_paid = member.total_paid_out()
    pending    = member.pending_payout_amount()

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

        item = MenuItem.objects.create(
            category_id   = category_id,
            name          = request.POST['name'],
            description   = request.POST.get('description', ''),
            price         = request.POST.get('price', '0.00') or '0.00',
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
        item.description = request.POST.get('description', '')
        item.price = request.POST.get('price', '0.00') or '0.00'
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
    client_filter = request.GET.get('client', '')
    
    # Order by ID descending so the newest added report is always right at the top
    reports = ManualReport.objects.all().order_by('-id')
    
    month_name = ''
    if month_filter:
        reports = reports.filter(event_date__month=month_filter)
        try:
            month_name = calendar.month_name[int(month_filter)]
        except:
            pass
            
    if year_filter:
        reports = reports.filter(event_date__year=year_filter)

    if client_filter:
        from django.db.models import Q
        reports = reports.filter(Q(site_name=client_filter) | Q(event_name=client_filter))
        
    totals = reports.aggregate(
        t_boys=Sum('boys_count'),
        t_bill=Sum('bill_amount'),
        t_received=Sum('amount_received'),
        t_profit=Sum('profit')
    )
        
    from bookings.models import Client
    all_clients = Client.objects.all().order_by('name')
        
    context = {
        'reports': reports,
        'totals': totals,
        'page': 'reports',
        'month_filter': month_filter,
        'month_name': month_name,
        'year_filter': year_filter,
        'client_filter': client_filter,
        'clients': all_clients,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'admin/reports.html', context)
    return render(request, 'admin/reports.html', context)

@admin_required
def admin_reports_pdf(request):
    from bookings.models import ManualReport
    from django.db.models import Sum
    from django.http import HttpResponse
    import calendar
    from .pdf_utils import generate_financial_reports_pdf
    
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', '')
    client_filter = request.GET.get('client', '')
    
    reports = ManualReport.objects.all().order_by('event_date')
    
    month_name = ''
    if month_filter:
        reports = reports.filter(event_date__month=month_filter)
        try:
            month_name = calendar.month_name[int(month_filter)]
        except:
            pass
            
    if year_filter:
        reports = reports.filter(event_date__year=year_filter)

    if client_filter:
        from django.db.models import Q
        reports = reports.filter(Q(site_name=client_filter) | Q(event_name=client_filter))
        
    totals = reports.aggregate(
        t_boys=Sum('boys_count'),
        t_bill=Sum('bill_amount'),
        t_received=Sum('amount_received'),
        t_profit=Sum('profit')
    )
    

    pdf_bytes = generate_financial_reports_pdf(reports, totals, month_name, year_filter, client_filter)
    
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = "Financial_Reports"
    if month_name: filename += f"_{month_name}"
    if year_filter: filename += f"_{year_filter}"
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    return response

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
                work_type = request.POST.get('work_type', 'day'),
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
            report.work_type = request.POST.get('work_type', 'day')
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
                    title = "MASTAN CATERING — Official Notice"
                    icon = f"{base_url}/static/images/logo.png"
                    link = f"{base_url}/staff/"
                    # FIX: Use data-only payload. NO notification block, NO AndroidNotification,
                    # NO WebpushNotification. This prevents the triple-notification bug where
                    # Android shows: 1 from notification block + 1 from WebpushNotification +
                    # 1 from the JS onBackgroundMessage handler = 3 popups for one notice.
                    # The Service Worker onBackgroundMessage in firebase-messaging-sw.js
                    # is the SINGLE place that shows the notification.
                    fcm_msg = messaging.MulticastMessage(
                        data={'title': title, 'body': body_text, 'link': link, 'icon': icon},
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
    from bookings.models import EventReport, Client
    
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', '')
    client_filter = request.GET.get('client', '')
    
    reports_qs = EventReport.objects.all().select_related('booking', 'submitted_by')
    
    if month_filter:
        reports_qs = reports_qs.filter(booking__event_date__month=month_filter)
    if year_filter:
        reports_qs = reports_qs.filter(booking__event_date__year=year_filter)
    if client_filter:
        reports_qs = reports_qs.filter(booking__name=client_filter)
    
    reports_qs = reports_qs.order_by('-booking__event_date', '-created_at')
    
    all_clients = Client.objects.all().order_by('name')
    
    # Simple pagination
    paginator = Paginator(reports_qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    context = {
        'reports': page_obj,
        'page': 'reports',
        'month_filter': month_filter,
        'year_filter': year_filter,
        'client_filter': client_filter,
        'clients': all_clients,
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'admin/event_reports_list.html', context)
    return render(request, 'admin/event_reports_list.html', context)

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
    Handle POST request with invoice JSON data.
    Instead of downloading immediately, it just saves to history and returns success.
    """
    if request.method == 'POST':
        import json
        try:
            if 'invoice_data' in request.POST:
                data = json.loads(request.POST.get('invoice_data'))
            else:
                data = json.loads(request.body)

            # ── Save invoice record to history ──────────────────────────────
            from core.models import InvoiceRecord
            from datetime import datetime
            import decimal
            
            items = data.get('items', [])
            total = sum(
                float(i.get('qty', 0)) * float(i.get('price', i.get('rate', 0)))
                for i in items if i.get('name')
            )
            
            event_date_str = data.get('event_date', '')
            event_date_obj = None
            if event_date_str:
                try:
                    event_date_obj = datetime.strptime(event_date_str, '%d-%b-%Y').date()
                except ValueError:
                    try:
                        event_date_obj = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass

            InvoiceRecord.objects.create(
                client_name=data.get('bill_to', ''),
                client_phone=data.get('contact', ''),
                event_date=event_date_obj,
                items_json=items,
                total_amount=round(total, 2),
                notes=json.dumps(data),  # Store full JSON for PDF generation
            )
            # ────────────────────────────────────────────────────────────────
            return JsonResponse({'ok': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return redirect('admin_manual_invoice')


# ─── Invoice History ─────────────────────────────────────────────────────────

@admin_required
def invoice_history(request):
    from core.models import InvoiceRecord
    from django.core.paginator import Paginator
    records = InvoiceRecord.objects.all()
    paginator = Paginator(records, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'admin/invoice_history.html', {'page_obj': page, 'page': 'reports'})


@admin_required
def invoice_history_download(request, pk):
    from core.models import InvoiceRecord
    record = get_object_or_404(InvoiceRecord, pk=pk)
    try:
        from .pdf_utils import build_invoice_pdf
        import json
        
        try:
            full_data = json.loads(record.notes) if record.notes else {}
        except json.JSONDecodeError:
            full_data = {}
            
        data = {
            'inv_no': full_data.get('inv_no', f'INV-{record.pk:04d}'),
            'date': full_data.get('date', record.created_at.strftime('%d-%b-%Y')),
            'site_name': full_data.get('site_name', ''),
            'bill_to': record.client_name,
            'contact': record.client_phone,
            'event_date': full_data.get('event_date', record.event_date.strftime('%d-%b-%Y') if record.event_date else ''),
            'items': record.items_json,
        }
        
        buffer = build_invoice_pdf(data)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Invoice_{record.pk}_{record.client_name}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f'Could not generate PDF: {e}')
        return redirect('admin_invoice_history')


@admin_required
def invoice_history_delete(request, pk):
    from core.models import InvoiceRecord
    if request.method == 'POST':
        try:
            record = get_object_or_404(InvoiceRecord, pk=pk)
            record.delete()
            messages.success(request, 'Invoice record deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting invoice: {e}')
    return redirect('admin_invoice_history')


# ─── Admin Notepad ───────────────────────────────────────────────────────────

@admin_required
def notepad(request):
    from core.models import AdminNote, NoteCategory
    if request.method == 'POST':
        title = request.POST.get('title', 'New Note').strip() or 'New Note'
        category_id = request.POST.get('category_id')
        note = AdminNote.objects.create(title=title, category_id=category_id if category_id else None)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'id': note.pk,
                'title': note.title,
                'content': note.content,
                'category_id': note.category_id,
                'created_at': note.created_at.strftime('%A, %d %B · %I:%M %p'),
                'updated_at': note.updated_at.strftime('%A, %d %B · %I:%M %p'),
            })
        return redirect('admin_notepad')
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'GET':
        qs = AdminNote.objects.select_related('category').all()
        cat_id = request.GET.get('category')
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        
        month = request.GET.get('month')
        if month:
            qs = qs.filter(updated_at__month=month)
            
        year = request.GET.get('year')
        if year:
            qs = qs.filter(updated_at__year=year)
            
        notes_data = [{
            'id': n.pk,
            'title': n.title,
            'content': n.content,
            'category_id': n.category_id,
            'updated_at_formatted': n.updated_at.strftime('%A, %d %B · %I:%M %p')
        } for n in qs]
        return JsonResponse({'notes': notes_data})

    notes = AdminNote.objects.all()
    categories = NoteCategory.objects.all()
    return render(request, 'admin/notepad.html', {'notes': notes, 'categories': categories, 'page': 'notepad'})


@admin_required
def note_save(request, pk):
    from core.models import AdminNote
    if request.method == 'POST':
        note = get_object_or_404(AdminNote, pk=pk)
        note.title = request.POST.get('title', note.title).strip() or 'New Note'
        note.content = request.POST.get('content', note.content)
        category_id = request.POST.get('category_id')
        if category_id:
            note.category_id = category_id
        else:
            note.category = None
        note.save()
        return JsonResponse({
            'ok': True,
            'updated_at': note.updated_at.strftime('%A, %d %B · %I:%M %p'),
        })
    return JsonResponse({'ok': False}, status=405)


@admin_required
def note_delete(request, pk):
    from core.models import AdminNote
    if request.method == 'POST':
        note = get_object_or_404(AdminNote, pk=pk)
        note.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
    return redirect('admin_notepad')

@admin_required
def note_category_add(request):
    from core.models import NoteCategory
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Category name is required'}, status=400)
        cat, created = NoteCategory.objects.get_or_create(name=name)
        return JsonResponse({'id': cat.pk, 'name': cat.name})
    return JsonResponse({'error': 'Invalid request'}, status=400)


def api_get_clients(request):
    """
    Returns a list of all clients for autocomplete.
    """
    from bookings.models import Client
    clients = Client.objects.all().values('name', 'phone')
    return JsonResponse(list(clients), safe=False)


# ── Dynamic Settings ────────────────────────────────────────────────────────
@admin_required
def admin_settings(request):
    return render(request, 'admin/settings_dashboard.html')

@admin_required
def locality_list(request):
    from staff.models import Locality
    localities = Locality.objects.all()
    return render(request, 'admin/locality_list.html', {'localities': localities, 'page': 'settings'})

@admin_required
def locality_add(request):
    from staff.models import Locality
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            Locality.objects.create(name=name)
            messages.success(request, 'Locality added successfully!')
            return redirect('admin_locality_list')
        messages.error(request, 'Locality name cannot be empty.')
    return render(request, 'admin/locality_form.html', {'page': 'settings'})

@admin_required
def locality_edit(request, pk):
    from staff.models import Locality
    locality = get_object_or_404(Locality, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            locality.name = name
            locality.save()
            messages.success(request, 'Locality updated successfully!')
            return redirect('admin_locality_list')
        messages.error(request, 'Locality name cannot be empty.')
    return render(request, 'admin/locality_form.html', {'item': locality, 'page': 'settings'})

@admin_required
def locality_delete(request, pk):
    if request.method == 'POST':
        from staff.models import Locality
        locality = get_object_or_404(Locality, pk=pk)
        locality.delete()
        messages.success(request, 'Locality deleted.')
    return redirect('admin_locality_list')

@admin_required
def client_list(request):
    from bookings.models import Client
    clients = Client.objects.all().order_by('name')
    return render(request, 'admin/client_list.html', {'clients': clients, 'page': 'settings'})

@admin_required
def client_add(request):
    from bookings.models import Client
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        if name:
            Client.objects.create(name=name, phone=phone)
            messages.success(request, 'Client added successfully!')
            return redirect('admin_client_list')
        messages.error(request, 'Client name cannot be empty.')
    return render(request, 'admin/client_form.html', {'page': 'settings'})

@admin_required
def client_edit(request, pk):
    from bookings.models import Client
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        if name:
            client.name = name
            client.phone = phone
            client.save()
            messages.success(request, 'Client updated successfully!')
            return redirect('admin_client_list')
        messages.error(request, 'Client name cannot be empty.')
    return render(request, 'admin/client_form.html', {'item': client, 'page': 'settings'})

@admin_required
def client_delete(request, pk):
    if request.method == 'POST':
        from bookings.models import Client
        client = get_object_or_404(Client, pk=pk)
        client.delete()
        messages.success(request, 'Client deleted.')
    return redirect('admin_client_list')


# ─── Terms & Conditions CRUD ────────────────────────────────────────────────

@admin_required
def terms_list(request):
    from core.models import TermAndCondition
    terms = TermAndCondition.objects.all()
    return render(request, 'admin/terms_list.html', {'terms': terms, 'page': 'settings'})


@admin_required
def term_add(request):
    from core.models import TermAndCondition
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            TermAndCondition.objects.create(text=text)
            messages.success(request, 'Term added successfully!')
            return redirect('admin_terms_list')
        messages.error(request, 'Term text cannot be empty.')
    return render(request, 'admin/term_form.html', {'item': None, 'page': 'settings'})


@admin_required
def term_edit(request, pk):
    from core.models import TermAndCondition
    term = get_object_or_404(TermAndCondition, pk=pk)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            term.text = text
            term.save()
            messages.success(request, 'Term updated successfully!')
            return redirect('admin_terms_list')
        messages.error(request, 'Term text cannot be empty.')
    return render(request, 'admin/term_form.html', {'item': term, 'page': 'settings'})


@admin_required
def term_delete(request, pk):
    from core.models import TermAndCondition
    if request.method == 'POST':
        term = get_object_or_404(TermAndCondition, pk=pk)
        term.delete()
        messages.success(request, 'Term deleted.')
    return redirect('admin_terms_list')


# ─── Invoice Items CRUD ─────────────────────────────────────────────────────

@admin_required
def invoice_items_list(request):
    from core.models import InvoiceItem
    items = InvoiceItem.objects.all()
    return render(request, 'admin/invoice_items_list.html', {'items': items, 'page': 'settings'})


@admin_required
def invoice_item_add(request):
    from core.models import InvoiceItem
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        price = request.POST.get('default_price', '0') or '0'
        if name:
            if InvoiceItem.objects.filter(name=name).exists():
                messages.error(request, f'Item "{name}" already exists.')
            else:
                InvoiceItem.objects.create(name=name, default_price=price)
                messages.success(request, 'Invoice item added!')
                return redirect('admin_invoice_items_list')
        else:
            messages.error(request, 'Item name cannot be empty.')
    return render(request, 'admin/invoice_item_form.html', {'item': None, 'page': 'settings'})


@admin_required
def invoice_item_edit(request, pk):
    from core.models import InvoiceItem
    inv_item = get_object_or_404(InvoiceItem, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        price = request.POST.get('default_price', '0') or '0'
        if name:
            inv_item.name = name
            inv_item.default_price = price
            inv_item.save()
            messages.success(request, 'Invoice item updated!')
            return redirect('admin_invoice_items_list')
        messages.error(request, 'Item name cannot be empty.')
    return render(request, 'admin/invoice_item_form.html', {'item': inv_item, 'page': 'settings'})


@admin_required
def invoice_item_delete(request, pk):
    from core.models import InvoiceItem
    if request.method == 'POST':
        inv_item = get_object_or_404(InvoiceItem, pk=pk)
        inv_item.delete()
        messages.success(request, 'Invoice item deleted.')
    return redirect('admin_invoice_items_list')


# ─── Invoice Items JSON API ─────────────────────────────────────────────────

def api_get_invoice_items(request):
    from core.models import InvoiceItem
    from django.http import JsonResponse
    items = list(InvoiceItem.objects.values('name', 'default_price'))
    # Make price serializable as float
    for item in items:
        item['price'] = float(item.pop('default_price'))
    return JsonResponse(items, safe=False)
