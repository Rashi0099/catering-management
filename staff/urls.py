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
    path('bookings/<int:pk>/apply/', views.staff_apply_booking, name='staff_apply_booking'),
    path('bookings/<int:pk>/cancel_request/', views.staff_cancel_request, name='staff_cancel_request'),
    path('bookings/<int:pk>/pdf/', views.staff_download_attendance, name='staff_download_attendance'),
    path('bookings/<int:pk>/report/', views.staff_submit_report, name='staff_submit_report'),
    path('bookings/<int:pk>/complete-task/', views.staff_complete_task, name='staff_complete_task'),
    path('payouts/', views.staff_payouts, name='staff_payouts'),
    path('profile/', views.staff_profile, name='staff_profile'),
    path('profile/upload-photo/', views.upload_profile_photo, name='upload_profile_photo'),
    path('terms/', views.staff_terms, name='staff_terms'),
]

