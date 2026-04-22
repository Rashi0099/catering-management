import re
import threading
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.files import File
from io import BytesIO
from PIL import Image
from bookings.models import Booking


def auto_complete_past_bookings():
    """
    Finds all 'confirmed' bookings with an event_date in the past
    and automatically marks them as 'completed'.
    Rate-limited to run once every 10 minutes.

    Uses individual .save() calls (not bulk update) so that completion
    side-effects fire correctly: staff.total_events_completed recalculation
    and Level-C promotion checks in admin_views.booking_detail.
    """
    lock_key = 'auto_complete_lock'
    if cache.get(lock_key):
        return

    today = timezone.now().date()
    past_confirmed = Booking.objects.filter(status='confirmed', event_date__lt=today)

    if past_confirmed.exists():
        # Process up to 10 at a time to avoid long-running requests
        for booking in past_confirmed[:10]:
            booking.status = 'completed'
            booking.save(update_fields=['status', 'updated_at'])

            # Recalculate completed count and check Level-C promotion for each assigned staff
            for s in booking.assigned_to.all():
                s.total_events_completed = s.bookings.filter(status='completed').count()
                s.save(update_fields=['total_events_completed'])

                if s.level == 'C':
                    from staff.models import PromotionRequest
                    day_count   = s.bookings.filter(status='completed', session='day').count()
                    night_count = s.bookings.filter(status='completed', session='night').count()
                    long_count  = s.bookings.filter(status='completed', is_long_work=True).count()
                    if day_count >= 10 and night_count >= 5 and long_count >= 5:
                        if not PromotionRequest.objects.filter(staff=s, status='pending').exists():
                            PromotionRequest.objects.create(
                                staff=s,
                                current_level='C',
                                requested_level='B'
                            )

        # Invalidate dashboard cache so counts update immediately
        cache.delete('admin_dashboard_stats')

    # Set lock for 10 minutes
    cache.set(lock_key, True, 600)



def get_pending_count():
    """Returns pending booking count, cached for 2 minutes."""
    count = cache.get('pending_booking_count')
    if count is None:
        count = Booking.objects.filter(status='pending').count()
        cache.set('pending_booking_count', count, 120)
    return count


def pending_count_context(request):
    """Context processor — injects pending_count into every template."""
    if request.path.startswith('/admin-panel/') and request.user.is_authenticated and request.user.is_staff:
        return {'pending_count': get_pending_count()}
    return {}


def validate_phone(phone):
    """
    Validates Indian phone numbers.
    Accepts: 10 digits, with optional +91 or 0 prefix.
    Returns cleaned 10-digit number or None if invalid.
    """
    if not phone:
        return None
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    # Remove +91 or 0 prefix
    cleaned = re.sub(r'^(\+91|91|0)', '', cleaned)
    # Must be exactly 10 digits starting with 6-9
    if re.fullmatch(r'[6-9]\d{9}', cleaned):
        return cleaned
    return None


def send_fcm_notification(staff, title, body, link=None):
    """
    Unified utility to send push notifications and handle stale token cleanup.
    """
    try:
        from firebase_admin import messaging
        tokens = list(staff.fcm_devices.values_list('token', flat=True))
        if not tokens:
            return None
        # Send purely as 'data' payload to bypass Firebase's visual handling
        # and force our service worker to construct the OS-level notification manually.
        message = messaging.MulticastMessage(
            data={
                'title': str(title),
                'body': str(body),
                'link': str(link or '/staff/'),
                'icon': '/static/images/logo.png'
            },
            android=messaging.AndroidConfig(priority='high'),
            webpush=messaging.WebpushConfig(headers={"Urgency": "high"}),
            tokens=tokens,
        )
        
        response = messaging.send_each_for_multicast(message)
        
        # Cleanup expired tokens
        if response.failure_count > 0:
            stale_tokens = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    stale_tokens.append(tokens[idx])
            
            if stale_tokens:
                staff.fcm_devices.filter(token__in=stale_tokens).delete()
        
        return response
    except Exception as e:
        print(f"FCM Notification Error: {e}")
        return None


def notify_admins(title, body, link='/admin-panel/'):
    """Send an FCM Multicast Web Push to all Admin Staff."""
    from staff.models import Staff
    admins = Staff.objects.filter(level='admin')
    for admin in admins:
        send_fcm_notification(admin, title, body, link=link)


def send_mail_background(subject, message, from_email, recipient_list, **kwargs):
    """Sends email asynchronously to prevent UI blocking."""
    thread = threading.Thread(
        target=send_mail,
        args=(subject, message, from_email, recipient_list),
        kwargs=kwargs
    )
    thread.start()




