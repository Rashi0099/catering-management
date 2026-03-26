from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.conf import settings
from .models import Booking, Testimonial


def booking_form(request):
    if request.method == 'POST':
        try:
            booking = Booking.objects.create(
                name=request.POST.get('name'),
                email=request.POST.get('email'),
                phone=request.POST.get('phone'),
                company=request.POST.get('company', ''),
                event_type=request.POST.get('event_type'),
                event_date=request.POST.get('event_date'),
                event_time=request.POST.get('event_time') or None,
                venue=request.POST.get('venue', ''),
                guest_count=int(request.POST.get('guest_count', 1)),
                budget=request.POST.get('budget') or None,
                dietary_requirements=request.POST.get('dietary_requirements', ''),
                special_requests=request.POST.get('special_requests', ''),
                message=request.POST.get('message', ''),
            )

            # Email notification to admin
            try:
                send_mail(
                    subject=f'🍽️ New Booking: {booking.get_event_type_display()} — {booking.name}',
                    message=f"""
New booking received on Catrin Boys website!

Client: {booking.name}
Email: {booking.email}
Phone: {booking.phone}
Event: {booking.get_event_type_display()}
Date: {booking.event_date}
Guests: {booking.guest_count}
Venue: {booking.venue or 'Not specified'}
Budget: {booking.budget or 'Not specified'}

Message: {booking.message}

View in admin: http://yourdomain.com/admin-panel/bookings/{booking.pk}/
                    """,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[settings.EMAIL_HOST_USER],
                    fail_silently=True,
                )
            except Exception:
                pass  # Don't break if email fails

            return redirect('booking_success')

        except Exception as e:
            return render(request, 'bookings/booking.html', {
                'error': 'Something went wrong. Please try again.',
                'post_data': request.POST,
            })

    testimonials = Testimonial.objects.filter(is_featured=True)[:3]
    return render(request, 'bookings/booking.html', {'testimonials': testimonials})


def booking_success(request):
    return render(request, 'bookings/success.html')
