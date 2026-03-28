from django import template
from bookings.models import EventApplication

register = template.Library()

@register.simple_tag
def get_pending_app_count():
    return EventApplication.objects.filter(status__in=['pending', 'cancel_requested']).count()
