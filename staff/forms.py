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
            'age': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Age', 'min': '18'}),
            'height': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "e.g. 5'9\""}),
            'blood_group': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Blood Group'}),
            'phone_1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number 1', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'phone_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number 2 (Optional)', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'guardian_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Guardian Name'}),
            'guardian_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Guardian Phone No.', 'pattern': '[0-9]{10}', 'title': 'Please enter a valid 10-digit phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email (Optional)'}),
            'place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Place / City'}),
            'education': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Highest Education'}),
            'aadhar_card_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Aadhar Card No.'}),
            'main_locality': forms.Select(attrs={'class': 'form-control', 'style': 'appearance: auto;'}),
            'coat_size': forms.Select(attrs={'class': 'form-control', 'style': 'appearance: auto;'}),
        }

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

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age < 18:
            raise forms.ValidationError("You must be at least 18 years old to apply.")
        return age
