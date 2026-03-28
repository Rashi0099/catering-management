from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Sum, Count, Q

from .models import Staff, StaffPayout, StaffAttendance
from bookings.models import Booking, BookingPayment


# ── Authentication ───────────────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_change_password(request):
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
    logout(request)
    return redirect('staff_login')


# ── Staff Dashboard ──────────────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_dashboard(request):
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
    })


# ── Staff Booking Management ─────────────────────────────────────────────────

@login_required(login_url='/staff/login/')
def staff_bookings(request):
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

    return render(request, 'staff/booking_detail.html', {
        'booking': booking,
        'payments': payments,
        'today': timezone.now().date(),
    })


@login_required(login_url='/staff/login/')
def staff_apply_booking(request, pk):
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
