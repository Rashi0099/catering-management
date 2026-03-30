from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.conf import settings
from menu.models import MenuItem
from bookings.models import Testimonial


def home(request):
    """Renders the homepage displaying featured menu items and testimonials."""
    featured_items = MenuItem.objects.filter(is_featured=True, is_available=True)[:6]
    testimonials   = Testimonial.objects.filter(is_featured=True)[:3]
    return render(request, 'core/home.html', {
        'featured_items': featured_items,
        'testimonials': testimonials,
    })


def about(request):
    """Renders the static About Us page."""
    return render(request, 'core/about.html')


def contact(request):
    """Handles the contact form submission and sends an email to the site owner."""
    contact_success = False
    if request.method == 'POST':
        name    = request.POST.get('name', '')
        phone   = request.POST.get('phone', '')
        message = request.POST.get('message', '')
        try:
            send_mail(
                subject=f'Contact Form: {name}',
                message=f"Name: {name}\nPhone: {phone}\n\nMessage:\n{message}",
                from_email=settings.EMAIL_HOST_USER or 'noreply@catrinboys.com',
                recipient_list=[settings.EMAIL_HOST_USER or 'noreply@catrinboys.com'],
                fail_silently=True,
            )
        except Exception:
            pass
        contact_success = True
    return render(request, 'core/contact.html', {'contact_success': contact_success})
