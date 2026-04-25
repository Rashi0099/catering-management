from django.shortcuts import render, redirect, reverse
from django.conf import settings
from .models import Testimonial
from .forms import BookingForm
from staff.forms import StaffApplicationForm

def booking_form(request):
    """Handles submission of both client event bookings and new staff applications securely."""
    event_form = BookingForm()
    staff_form = StaffApplicationForm()
    error = None

    if request.method == 'POST':
        # Anti-spam Honeypot Check
        if request.POST.get('website', '').strip():
            error = 'Suspicious activity detected. Submission blocked.'
        
        elif 'submit_event' in request.POST:
            event_form = BookingForm(request.POST)
            if event_form.is_valid():
                try:
                    booking = event_form.save()
                    try:
                        from core.utils import send_mail_background
                        send_mail_background(
                            subject=f'🍽️ New Booking: {booking.get_event_type_display()} — {booking.name}',
                            message=f"New booking received!\n\nClient: {booking.name}\nEmail: {booking.email}\nPhone: {booking.phone}\nEvent: {booking.get_event_type_display()}\nDate: {booking.event_date}\nView in admin: /admin-panel/bookings/{booking.pk}/\n",
                            from_email=settings.EMAIL_HOST_USER,
                            recipient_list=[settings.EMAIL_HOST_USER],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                    return redirect(reverse('booking_success') + '?type=event')
                except Exception as e:
                    error = 'Something went wrong processing your event booking. Please try again.'
            else:
                error = 'Please correct the errors in the Event Booking form.'

        elif 'submit_staff' in request.POST:
            # Added request.FILES to ensure images are persisted and validated
            staff_form = StaffApplicationForm(request.POST, request.FILES)
            if staff_form.is_valid():
                try:
                    application = staff_form.save(commit=False)
                    application.status = 'pending'  # pending admin approval directly
                    application.save()
                    return redirect(reverse('booking_success') + '?type=staff')
                except Exception as e:
                    error = 'Something went wrong processing your staff application. Please try again.'
            else:
                error = 'Please correct the errors in the Staff Application form.'



    testimonials = Testimonial.objects.filter(is_featured=True)[:3]
    return render(request, 'bookings/booking.html', {
        'testimonials': testimonials,
        'event_form': event_form,
        'staff_form': staff_form,
        'error': error,
    })

def booking_success(request):
    """Displays a success message page with context-specific text."""
    success_type = request.GET.get('type', 'event')
    return render(request, 'bookings/success.html', {'type': success_type})
