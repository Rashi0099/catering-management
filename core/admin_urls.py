from django.urls import path
from . import admin_views

urlpatterns = [
    path('',                              admin_views.dashboard,             name='admin_dashboard'),
    path('login/',                        admin_views.admin_login,           name='admin_login'),
    path('logout/',                       admin_views.admin_logout,          name='admin_logout'),

    # Bookings
    path('bookings/',                     admin_views.bookings_list,         name='admin_bookings'),
    path('bookings/new/',                 admin_views.admin_create_booking,  name='admin_create_booking'),
    path('bookings/<int:pk>/',            admin_views.booking_detail,        name='admin_booking_detail'),
    path('bookings/<int:pk>/download-attendance/', admin_views.download_attendance, name='admin_download_attendance'),
    path('bookings/<int:pk>/status/',     admin_views.update_booking_status, name='admin_update_status'),

    # Staff  — payout URL MUST be before <int:pk>/ to avoid shadowing
    path('staff/',                        admin_views.staff_list,            name='admin_staff'),
    path('staff-applications/',           admin_views.staff_applications,    name='admin_staff_applications'),
    path('staff-applications/<int:pk>/<str:action>/', admin_views.handle_staff_application, name='admin_handle_staff_application'),
    path('staff-requests/',               admin_views.staff_requests,        name='admin_staff_requests'),
    path('staff/add/',                    admin_views.staff_add,             name='admin_staff_add'),
    path('staff/<int:pk>/edit/',          admin_views.staff_edit,            name='admin_staff_edit'),
    path('staff/payout/<int:pk>/pay/',    admin_views.mark_payout_paid,      name='admin_payout_paid'),
    path('staff/<int:pk>/',              admin_views.staff_detail,           name='admin_staff_detail'),
    path('bookings/<int:pk>/application/<int:app_id>/<str:action>/', admin_views.handle_application, name='admin_handle_application'),

    # Menu
    path('menu/',                         admin_views.menu_list,             name='admin_menu'),
    path('menu/add/',                     admin_views.menu_add,              name='admin_menu_add'),
    path('menu/<int:pk>/delete/',         admin_views.menu_delete,           name='admin_menu_delete'),

    # Gallery & Team
    path('gallery/',                      admin_views.gallery_list,          name='admin_gallery'),
    path('team/',                         admin_views.team_page,             name='admin_team'),
]
