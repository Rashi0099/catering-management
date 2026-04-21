import re
from django.utils import timezone
from django.core.cache import cache
from bookings.models import Booking


def auto_complete_past_bookings():
    """
    Finds all 'confirmed' bookings with an event_date in the past
    and automatically marks them as 'completed'.
    """
    today = timezone.now().date()
    past_confirmed = Booking.objects.filter(status='confirmed', event_date__lt=today)
    if past_confirmed.exists():
        past_confirmed.update(status='completed')
        # Invalidate dashboard cache so counts update immediately
        cache.delete('admin_dashboard_stats')


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

