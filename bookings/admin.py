from django.contrib import admin
from .models import Booking, Testimonial


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'event_date', 'guest_count', 'status', 'created_at']
    list_filter = ['status', 'event_type', 'event_date']
    list_editable = ['status']
    search_fields = ['name', 'email', 'phone']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Client Info', {'fields': ('name', 'email', 'phone', 'company')}),
        ('Event Details', {'fields': ('event_type', 'event_date', 'event_time', 'venue', 'location_name', 'location_link', 'guest_count', 'budget')}),
        ('Requirements', {'fields': ('dietary_requirements', 'special_requests', 'message')}),
        ('Admin', {'fields': ('status', 'admin_notes', 'quoted_price', 'assigned_to', 'is_published', 'publish_locality', 'created_at', 'updated_at')}),
    )

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        was_published = False
        if not is_new:
            try:
                # Use current instance from DB to check previous state
                was_published = self.model.objects.get(pk=obj.pk).is_published
            except self.model.DoesNotExist:
                pass
                
        super().save_model(request, obj, form, change)
        
        # Trigger Web Push Notification if newly published
        if obj.is_published and not was_published:
            try:
                from webpush import send_user_notification
                from django.contrib.auth import get_user_model
                
                location = obj.location_name or obj.venue or 'TBA'
                payload = {
                    "head": "New Shift Available!",
                    "body": f"{obj.get_event_type_display()} on {obj.event_date} at {location}.",
                    "icon": "/static/images/logo.png",
                    "url": "/staff/bookings/"
                }
                
                Staff = get_user_model()
                targets = Staff.objects.filter(is_active=True)
                if obj.publish_locality and obj.publish_locality != 'all':
                    targets = targets.filter(main_locality=obj.publish_locality)
                    
                for staff in targets:
                    try:
                        send_user_notification(user=staff, payload=payload, ttl=1000)
                    except Exception:
                        pass
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Web Push Error: {e}")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'event_type', 'rating', 'is_featured']
    list_editable = ['is_featured']
