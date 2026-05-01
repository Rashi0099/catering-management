from django.core.cache import cache
from bookings.models import Booking

def admin_pending_count(request):
    """
    Returns the pending bookings count for rendering in the admin side menu.
    FIX: Now shares the same 'pending_booking_count' cache key as core.utils.get_pending_count()
    to avoid 2 separate DB queries per admin page load.
    Cached for 120 seconds.
    """
    if request.path.startswith('/admin-panel/') and request.user.is_authenticated:
        count = cache.get('pending_booking_count')
        if count is None:
            count = Booking.objects.filter(status='pending').count()
            cache.set('pending_booking_count', count, 120)
        return {'pending_count': count}
    return {}
