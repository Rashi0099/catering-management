from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin-panel/login/')(view_func)
from django.http import JsonResponse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from bookings.models import Booking, BookingPayment
from menu.models import MenuItem, MenuCategory
from gallery.models import GalleryImage
from staff.models import Staff, StaffPayout


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
            booking.status       = request.POST.get('status', booking.status)
            booking.admin_notes  = request.POST.get('admin_notes', '')
            booking.quoted_price = request.POST.get('quoted_price') or None
            booking.save()
            # Assign staff
            staff_ids = request.POST.getlist('assigned_to')
            booking.assigned_to.set(staff_ids)
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
        return redirect('admin_booking_detail', pk=pk)

    context = {
        'booking': booking,
        'all_staff': all_staff,
        'payments': payments,
        'today': timezone.now().date(),
        'page': 'bookings',
        'pending_count': Booking.objects.filter(status='pending').count(),
    }
    return render(request, 'admin/booking_detail.html', context)


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
            booking.status = new_status
            booking.save()
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# ── Staff Management (ADMIN) ─────────────────────────────────────────────────

@admin_required
def staff_list(request):
    staff = Staff.objects.filter(is_active=True).annotate(
        booking_count=Count('bookings', distinct=True)
    ).order_by('full_name')
    
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
        role = request.POST['role']
        daily_rate = request.POST.get('daily_rate', 0)
        phone = request.POST.get('phone', '')
        email = request.POST.get('email', '')

        try:
            from staff.models import generate_staff_id
            # create_user expects staff_id explicitly
            new_id = generate_staff_id()
            
            member = Staff.objects.create_user(
                staff_id=new_id,
                password='password123',
                full_name=full_name,
                role=role,
                daily_rate=daily_rate,
                phone=phone,
                email=email
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
