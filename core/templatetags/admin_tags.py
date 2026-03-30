from django import template
from bookings.models import EventApplication, Booking
from staff.models import StaffApplication, PromotionRequest

register = template.Library()

@register.simple_tag
def get_pending_app_count():
    return EventApplication.objects.filter(status__in=['pending', 'cancel_requested']).count()

@register.simple_tag
def get_pending_staff_apps_count():
    return StaffApplication.objects.filter(status='pending').count()

@register.simple_tag
def get_pending_promotions_count():
    return PromotionRequest.objects.filter(status='pending').count()

@register.simple_tag
def get_pending_bookings_count():
    return Booking.objects.filter(status='pending').count()
