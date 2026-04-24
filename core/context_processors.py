from django.core.cache import cache
from bookings.models import Booking

def admin_pending_count(request):
    """
    Returns the pending bookings count for rendering in the admin side menu.
    Cached for 60 seconds to prevent DB scans on every page reload.
    """
    if request.path.startswith('/admin-panel/'):
        count = cache.get('pending_bookings_count')
        if count is None:
            count = Booking.objects.filter(status='pending').count()
            cache.set('pending_bookings_count', count, 60)
        return {'pending_count': count}
    return {}
