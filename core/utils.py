import re
import threading
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import send_mail
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
    past_events = Booking.objects.filter(status__in=['pending', 'confirmed'], event_date__lt=today)

    if past_events.exists():
        # Process up to 50 at a time to avoid long-running requests
        for booking in past_events[:50]:
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
        BASE_URL = "https://mastan.in"
        tokens = list(set(staff.fcm_devices.values_list('token', flat=True)))
        if not tokens:
            return None
        
        # Cleanup potential duplicate tokens from other users if any
        # (Already handled in save_fcm_token view, but safety first)
        
        icon = f"{BASE_URL}/static/images/logo.png"
        badge = f"{BASE_URL}/static/icons/icon-192x192.png"
        abs_link = link if (link and link.startswith('http')) else f"{BASE_URL}{link or '/staff/'}"
        
        message = messaging.MulticastMessage(
            # Using data-only payload to prevent double OS + Browser notifications
            data={
                'title': str(title),
                'body': str(body),
                'link': abs_link,
                'icon': icon
            },
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
    """Send an FCM push notification to all admin staff members."""
    from staff.models import Staff
    admins = Staff.objects.filter(is_staff=True, is_active=True)
    for admin in admins:
        send_fcm_notification(admin, title, body, link=link)


# Alias — used by admin_views.py and staff/views.py attendance update handlers
send_push_notification = send_fcm_notification


def _notify_all_task(title, body, link):
    """Internal task function to broadcast FCM to all active staff."""
    from firebase_admin import messaging
    from staff.models import FCMDevice
    BASE_URL = "https://mastan.in"
    icon = f"{BASE_URL}/static/images/logo.png"
    abs_link = link if (link and link.startswith('http')) else f"{BASE_URL}{link or '/staff/'}"
    
    # Get all tokens for active staff
    devices = FCMDevice.objects.filter(staff__is_active=True).values_list('token', flat=True)
    tokens = list(devices)
    if not tokens:
        return
        
    chunk_size = 500 # FCM MulticastMessage supports up to 500 tokens at a time
    for i in range(0, len(tokens), chunk_size):
        chunk_tokens = tokens[i:i + chunk_size]
        try:
            message = messaging.MulticastMessage(
                # notification block = Android Chrome shows native OS-level notification
                notification=messaging.Notification(
                    title=str(title),
                    body=str(body),
                ),
                data={
                    'title': str(title),
                    'body': str(body),
                    'link': abs_link,
                    'icon': icon
                },
                # Android-specific: override icon and deep-link URL
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        icon=f"{BASE_URL}/static/images/logo.png",
                        badge=f"{BASE_URL}/static/icons/icon-192x192.png",
                    ),
                    fcm_options=messaging.WebpushFCMOptions(
                        link=abs_link
                    ),
                ),
                tokens=chunk_tokens,
            )
            response = messaging.send_each_for_multicast(message)
            
            if response.failure_count > 0:
                stale_tokens = [chunk_tokens[idx] for idx, resp in enumerate(response.responses) if not resp.success]
                if stale_tokens:
                    FCMDevice.objects.filter(token__in=stale_tokens).delete()
        except Exception as e:
            print(f"FCM Bulk Background Error: {e}")

def notify_all_staff_background(title, body, link='/staff/dashboard/'):
    """Sends global push notification asynchronously to all active staff"""
    thread = threading.Thread(
        target=_notify_all_task,
        args=(title, body, link)
    )
    thread.start()


def send_mail_background(subject, message, from_email, recipient_list, **kwargs):
    """Sends email asynchronously to prevent UI blocking."""
    thread = threading.Thread(
        target=send_mail,
        args=(subject, message, from_email, recipient_list),
        kwargs=kwargs
    )
    thread.start()
