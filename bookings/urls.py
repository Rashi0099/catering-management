from django.urls import path
from . import views

urlpatterns = [
    path('', views.booking_form, name='booking'),
    path('verify-otp/<int:pk>/', views.verify_staff_otp, name='verify_staff_otp'),
    path('success/', views.booking_success, name='booking_success'),
]
