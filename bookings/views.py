import random
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from .models import Booking, Testimonial
from .forms import BookingForm
from staff.models import StaffApplication
from staff.forms import StaffApplicationForm

def send_fast2sms_otp(phone, otp):
    """
    Mock OTP implementation for testing.
    Prints the OTP to the console instead of sending a real SMS.
    """
    print("\n" + "=" * 40)
   
    print(f"To: {phone}")
    print(f"OTP: {otp}")
    print("=" * 40 + "\n")
    return True


def booking_form(request):
    """Handles submission of both client event bookings and new staff applications securely."""
    event_form = BookingForm()
    staff_form = StaffApplicationForm()
    error = None

    if request.method == 'POST':
        if 'submit_event' in request.POST:
            event_form = BookingForm(request.POST)
            if event_form.is_valid():
                try:
                    booking = event_form.save()
                    try:
                        send_mail(
                            subject=f'🍽️ New Booking: {booking.get_event_type_display()} — {booking.name}',
                            message=f"New booking received!\n\nClient: {booking.name}\nEmail: {booking.email}\nPhone: {booking.phone}\nEvent: {booking.get_event_type_display()}\nDate: {booking.event_date}\nView in admin: /admin-panel/bookings/{booking.pk}/\n",
                            from_email=settings.EMAIL_HOST_USER,
                            recipient_list=[settings.EMAIL_HOST_USER],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                    return redirect('booking_success')
                except Exception as e:
                    error = 'Something went wrong processing your event booking. Please try again.'
            else:
                error = 'Please correct the errors in the Event Booking form.'

        elif 'submit_staff' in request.POST:
            staff_form = StaffApplicationForm(request.POST)
            if staff_form.is_valid():
                try:
                    application = staff_form.save(commit=False)
                    application.status = 'unverified'
                    application.save()
                    
                    # Generate OTP
                    otp = str(random.randint(1000, 9999))
                    request.session[f'staff_otp_{application.pk}'] = otp
                    
                    # Send Real SMS
                    sms_sent = send_fast2sms_otp(application.phone_1, otp)
                    if not sms_sent:
                        application.delete()
                        error = 'Failed to send OTP to your phone number. Please check your number and try again.'
                    else:
                        return redirect('verify_staff_otp', pk=application.pk)
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

def verify_staff_otp(request, pk):
    """Verifies the OTP sent to a staff applicant's phone number."""
    application = get_object_or_404(StaffApplication, pk=pk)
    
    # If already verified, don't let them do it again
    if application.status != 'unverified':
        return redirect('booking_success')
        
    error = None
    if request.method == 'POST':
        otp_entered = request.POST.get('otp')
        valid_otp = request.session.get(f'staff_otp_{application.pk}')
        
        if valid_otp and valid_otp == otp_entered:
            # Success
            application.status = 'pending' # Pending admin approval
            application.save()
            if f'staff_otp_{application.pk}' in request.session:
                del request.session[f'staff_otp_{application.pk}']
                
            return redirect('booking_success')
        else:
            error = "Invalid or expired OTP. Please try again."
            
    return render(request, 'bookings/verify_otp.html', {
        'application': application,
        'error': error
    })


def booking_success(request):
    """Displays a success message page after successful form submission."""
    return render(request, 'bookings/success.html')
