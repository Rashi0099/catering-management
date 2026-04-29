from django.shortcuts import render
from django.conf import settings
from menu.models import MenuItem
from bookings.models import Testimonial


def csrf_failure(request, reason=''):
    """Custom CSRF failure page — shown when the CSRF check fails."""
    return render(request, 'core/403_csrf.html', {'reason': reason}, status=403)

def home(request):
    """Renders the homepage displaying featured menu items, testimonials, and gallery images."""
    from gallery.models import GalleryImage
    featured_items = MenuItem.objects.select_related('category').filter(is_featured=True, is_available=True).order_by('?')[:6]
    testimonials   = Testimonial.objects.filter(is_featured=True)[:3]
    gallery_images = GalleryImage.objects.all().order_by('-id')[:5]
    contact_flag   = request.GET.get('contact', '')   # 'success' or 'error'
    return render(request, 'core/home.html', {
        'featured_items':    featured_items,
        'testimonials':      testimonials,
        'gallery_images':    gallery_images,
        'contact_success':   contact_flag == 'success',
        'contact_error':     contact_flag == 'error',
    })





CONTACT_EMAIL = 'mastanboys999@gmail.com'

def contact(request):
    """Handles the contact form submission and sends an email to mastanboys999@gmail.com."""
    contact_success = False
    contact_error   = False
    if request.method == 'POST':
        name    = request.POST.get('name', '').strip()
        phone   = request.POST.get('phone', '').strip()
        email   = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()
        source  = request.POST.get('source', 'contact')  # 'home' or 'contact'
        
        if name and message:
            body = (
                f"New enquiry from the website contact form.\n"
                f"───────────────────────────────\n"
                f"Name    : {name}\n"
                f"Phone   : {phone or '—'}\n"
                f"Email   : {email or '—'}\n"
                f"───────────────────────────────\n"
                f"Message :\n{message}"
            )
            try:
                from core.utils import send_mail_background
                send_mail_background(
                    subject=f'[Mastan Catering] Enquiry from {name}',
                    message=body,
                    from_email=settings.EMAIL_HOST_USER or CONTACT_EMAIL,
                    recipient_list=[CONTACT_EMAIL],
                    fail_silently=True,
                )
                contact_success = True
            except Exception:
                contact_error = True
        else:
            contact_error = True
        
        if source == 'home':
            # Redirect back to home with success flag
            from django.http import HttpResponseRedirect
            from django.urls import reverse
            flag = 'success' if contact_success else 'error'
            return HttpResponseRedirect(reverse('home') + f'?contact={flag}#s-contact')
        
    return render(request, 'core/contact.html', {
        'contact_success': contact_success,
        'contact_error': contact_error,
    })

def manifest(request):
    """Dynamically serves manifest.json based on query parameters."""
    start_url = request.GET.get('start_url', '/')
    name = request.GET.get('name', "Mastan Catering")
    short_name = request.GET.get('short_name', "Mastan")
    return render(request, 'manifest.json', {
        'start_url': start_url,
        'name': name,
        'short_name': short_name,
    }, content_type='application/json')
