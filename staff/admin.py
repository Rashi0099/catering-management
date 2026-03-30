from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Staff, StaffPayout, StaffAttendance
from .forms import StaffCreationForm

@admin.register(Staff)
class StaffAdmin(UserAdmin):
    add_form = StaffCreationForm
    list_display  = ['staff_id', 'full_name', 'level', 'total_events_completed', 'daily_rate', 'is_active']
    list_filter   = ['level', 'is_active']
    search_fields = ['staff_id', 'full_name', 'email', 'phone']
    ordering      = ['full_name']

    fieldsets = (
        ('Login', {'fields': ('staff_id', 'password')}),
        ('Personal', {'fields': ('full_name', 'email', 'phone', 'photo')}),
        ('Level & Pay', {'fields': ('level', 'total_events_completed', 'daily_rate', 'commission_pct')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('staff_id', 'full_name', 'level', 'daily_rate', 'password1', 'password2'),
        }),
    )


@admin.register(StaffPayout)
class StaffPayoutAdmin(admin.ModelAdmin):
    list_display  = ['staff', 'payout_type', 'amount', 'status', 'paid_on', 'paid_by']
    list_filter   = ['status', 'payout_type']
    list_editable = ['status']
    search_fields = ['staff__full_name', 'staff__staff_id']


@admin.register(StaffAttendance)
class StaffAttendanceAdmin(admin.ModelAdmin):
    list_display = ['staff', 'date', 'booking', 'status', 'hours']
    list_filter  = ['status', 'date']
