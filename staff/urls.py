from django.urls import path
from . import views

urlpatterns = [
    path('login/',            views.staff_login,           name='staff_login'),
    path('logout/',           views.staff_logout,          name='staff_logout'),
    path('password/',         views.staff_change_password, name='staff_change_password'),
    path('',                  views.staff_dashboard,       name='staff_dashboard'),
    path('bookings/',         views.staff_bookings,        name='staff_bookings'),
    path('bookings/new/',     views.staff_create_booking,  name='staff_create_booking'),
    path('bookings/<int:pk>/',views.staff_booking_detail,  name='staff_booking_detail'),
    path('bookings/<int:pk>/claim/', views.staff_claim_booking, name='staff_claim_booking'),
    path('payouts/',          views.staff_payouts,         name='staff_payouts'),
]
