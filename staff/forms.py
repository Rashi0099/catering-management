from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Staff

class StaffCreationForm(UserCreationForm):
    class Meta:
        model = Staff
        fields = ('staff_id', 'full_name', 'role', 'daily_rate', 'commission_pct')
