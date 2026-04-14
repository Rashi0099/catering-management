from django.urls import path
from . import views

urlpatterns = [
    path('', views.booking_form, name='booking'),
    path('success/', views.booking_success, name='booking_success'),
]
