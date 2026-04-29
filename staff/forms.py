from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Staff, StaffApplication

class StaffCreationForm(UserCreationForm):
    class Meta:
        model = Staff
        fields = ('staff_id', 'full_name', 'level', 'daily_rate', 'commission_pct')

class StaffApplicationForm(forms.ModelForm):
    class Meta:
        model = StaffApplication
        exclude = ['status']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-control', 'style': 'appearance: auto;'}),
            'height': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "e.g. 5'9\""}),
            'blood_group': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Blood Group'}),
            'phone_1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number 1', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'phone_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number 2 (Optional)', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'guardian_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Guardian Name'}),
            'guardian_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Guardian Phone No.', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email (Optional)'}),
            'home_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Home Address / City'}),
            'education': forms.Select(attrs={'class': 'form-control', 'style': 'appearance: auto;'}),
            'main_locality': forms.TextInput(attrs={'class': 'form-control', 'list': 'locality-list', 'placeholder': 'Select or type area'}),
            'coat_size': forms.Select(attrs={'class': 'form-control', 'style': 'appearance: auto;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Explicitly enforce education choices from model to ensure no stale data appears
        self.fields['education'].choices = [('', 'Select Education')] + Staff.EDUCATION_CHOICES
        
        from .models import Locality
        try:
            self.localities = list(Locality.objects.all())
        except Exception:
            self.localities = []

    def clean_phone_1(self):
        phone = self.cleaned_data.get('phone_1')
        if not phone.isdigit() or len(phone) < 10:
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return phone

    def clean_guardian_phone(self):
        phone = self.cleaned_data.get('guardian_phone')
        if not phone.isdigit() or len(phone) < 10:
            raise forms.ValidationError("Enter a valid 10-digit guardian phone number.")
        return phone

    def clean_phone_2(self):
        phone = self.cleaned_data.get('phone_2')
        if phone and (not phone.isdigit() or len(phone) < 10):
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return phone

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if not dob:
            raise forms.ValidationError("Date of birth is required.")
        from datetime import date
        today = date.today()
        calculated_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if calculated_age < 18:
            raise forms.ValidationError(f"You must be at least 18 years old to apply (calculated age: {calculated_age}).")
        return dob
