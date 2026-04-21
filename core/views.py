from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.conf import settings
from menu.models import MenuItem
from bookings.models import Testimonial


def csrf_failure(request, reason=''):
    """Custom CSRF failure page — shown when the CSRF check fails."""
    return render(request, 'core/403_csrf.html', {'reason': reason}, status=403)

def home(request):
    """Renders the homepage displaying featured menu items and testimonials."""
    featured_items = MenuItem.objects.filter(is_featured=True, is_available=True)[:6]
    testimonials   = Testimonial.objects.filter(is_featured=True)[:3]
    return render(request, 'core/home.html', {
        'featured_items': featured_items,
        'testimonials': testimonials,
    })





def contact(request):
    """Handles the contact form submission and sends an email to the site owner."""
    contact_success = False
    if request.method == 'POST':
        name    = request.POST.get('name', '')
        phone   = request.POST.get('phone', '')
        message = request.POST.get('message', '')
        try:
            from core.utils import send_mail_background
            send_mail_background(
                subject=f'Contact Form: {name}',
                message=f"Name: {name}\nPhone: {phone}\n\nMessage:\n{message}",
                from_email=settings.EMAIL_HOST_USER or 'noreply@mastanscatering.com',
                recipient_list=[settings.EMAIL_HOST_USER or 'noreply@mastanscatering.com'],
                fail_silently=True,
            )
        except Exception:
            pass
        contact_success = True
    return render(request, 'core/contact.html', {'contact_success': contact_success})

def manifest(request):
    """Dynamically serves manifest.json based on query parameters."""
    start_url = request.GET.get('start_url', '/')
    name = request.GET.get('name', "Mastan's Catering")
    short_name = request.GET.get('short_name', "Mastan")
    return render(request, 'manifest.json', {
        'start_url': start_url,
        'name': name,
        'short_name': short_name,
    }, content_type='application/json')
