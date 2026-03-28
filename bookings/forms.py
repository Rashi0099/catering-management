from django import forms
from .models import Booking
from django.utils import timezone
import datetime

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['name', 'email', 'phone', 'company', 'event_type', 'event_date', 
                  'event_time', 'venue', 'guest_count', 'budget', 'dietary_requirements', 
                  'special_requests', 'message']

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone.isdigit() or len(phone) < 10:
            raise forms.ValidationError("Enter a valid phone number with at least 10 digits.")
        return phone

    def clean_event_date(self):
        event_date = self.cleaned_data.get('event_date')
        if event_date and event_date < timezone.now().date():
            raise forms.ValidationError("Event date cannot be in the past.")
        return event_date

    def clean_guest_count(self):
        guest_count = self.cleaned_data.get('guest_count')
        if guest_count is None or guest_count < 1:
            raise forms.ValidationError("Guest count must be at least 1.")
        return guest_count
