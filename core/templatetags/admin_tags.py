from django import template
from django.core.cache import cache
from bookings.models import EventApplication, Booking
from staff.models import StaffApplication, PromotionRequest

register = template.Library()

@register.simple_tag
def get_pending_app_count():
    count = cache.get('sidebar_pending_app_count')
    if count is None:
        count = EventApplication.objects.filter(status__in=['pending', 'cancel_requested']).count()
        cache.set('sidebar_pending_app_count', count, 60)
    return count

@register.simple_tag
def get_pending_staff_apps_count():
    count = cache.get('sidebar_pending_staff_apps_count')
    if count is None:
        count = StaffApplication.objects.filter(status='pending').count()
        cache.set('sidebar_pending_staff_apps_count', count, 60)
    return count

@register.simple_tag
def get_pending_promotions_count():
    count = cache.get('sidebar_pending_promotions_count')
    if count is None:
        count = PromotionRequest.objects.filter(status='pending').count()
        cache.set('sidebar_pending_promotions_count', count, 60)
    return count

@register.simple_tag
def get_pending_bookings_count():
    count = cache.get('sidebar_pending_bookings_count')
    if count is None:
        count = Booking.objects.filter(status='pending').count()
        cache.set('sidebar_pending_bookings_count', count, 60)
    return count
