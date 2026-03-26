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
        ('Event Details', {'fields': ('event_type', 'event_date', 'event_time', 'venue', 'guest_count', 'budget')}),
        ('Requirements', {'fields': ('dietary_requirements', 'special_requests', 'message')}),
        ('Admin', {'fields': ('status', 'admin_notes', 'quoted_price', 'assigned_to', 'created_at', 'updated_at')}),
    )


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'event_type', 'rating', 'is_featured']
    list_editable = ['is_featured']
