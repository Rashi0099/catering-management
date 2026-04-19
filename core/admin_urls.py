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
    path('bookings/<int:pk>/edit/',       admin_views.admin_edit_booking,    name='admin_edit_booking'),
    path('bookings/<int:pk>/publish/',    admin_views.admin_publish_booking, name='admin_publish_booking'),
    path('bookings/<int:pk>/download-attendance/', admin_views.download_attendance, name='admin_download_attendance'),
    path('bookings/<int:pk>/status/',     admin_views.update_booking_status, name='admin_update_status'),

    # Staff  — payout URL MUST be before <int:pk>/ to avoid shadowing
    path('staff/',                        admin_views.staff_list,            name='admin_staff'),
    path('staff-applications/',           admin_views.staff_applications,    name='admin_staff_applications'),
    path('staff-applications/<int:pk>/<str:action>/', admin_views.handle_staff_application, name='admin_handle_staff_application'),
    path('staff-requests/',               admin_views.staff_requests,        name='admin_staff_requests'),
    path('staff-promotions/',             admin_views.staff_promotions,      name='admin_staff_promotions'),
    path('staff-promotions/<int:pk>/<str:action>/', admin_views.handle_promotion, name='admin_handle_promotion'),
    path('staff/add/',                    admin_views.staff_add,             name='admin_staff_add'),
    path('staff/<int:pk>/edit/',          admin_views.staff_edit,            name='admin_staff_edit'),
    path('staff/payout/<int:pk>/pay/',    admin_views.mark_payout_paid,      name='admin_payout_paid'),
    path('staff/<int:pk>/',              admin_views.staff_detail,           name='admin_staff_detail'),
    path('staff-notice/',                 admin_views.staff_notice,          name='admin_staff_notice'),
    path('bookings/<int:pk>/application/<int:app_id>/<str:action>/', admin_views.handle_application, name='admin_handle_application'),


    # Menu
    path('menu/',                         admin_views.menu_list,             name='admin_menu'),
    path('menu/add/',                     admin_views.menu_add,              name='admin_menu_add'),
    path('menu/<int:pk>/edit/',           admin_views.menu_edit,             name='admin_menu_edit'),
    path('menu/<int:pk>/delete/',         admin_views.menu_delete,           name='admin_menu_delete'),
    path('menu/category/<int:pk>/delete/',admin_views.menu_category_delete,  name='admin_menu_category_delete'),

    # Gallery & Team
    path('gallery/',                      admin_views.gallery_list,          name='admin_gallery'),
    path('gallery/add/',                  admin_views.gallery_add,           name='admin_gallery_add'),
    path('gallery/<int:pk>/edit/',        admin_views.gallery_edit,          name='admin_gallery_edit'),
    path('gallery/<int:pk>/delete/',      admin_views.gallery_delete,        name='admin_gallery_delete'),
    path('gallery/category/<int:pk>/delete/', admin_views.gallery_category_delete, name='admin_gallery_category_delete'),
    path('team/',                         admin_views.team_page,             name='admin_team'),

    # Reports & Invoice
    path('reports/',                      admin_views.admin_reports,         name='admin_reports'),
    path('reports/event-reports/',        admin_views.event_reports_list,    name='admin_event_reports'),
    path('reports/event-reports/<int:pk>/', admin_views.event_report_detail,  name='admin_event_report_detail'),
    path('reports/add/',                  admin_views.admin_report_add,      name='admin_report_add'),
    path('reports/<int:pk>/edit/',        admin_views.admin_report_edit,     name='admin_report_edit'),
    path('reports/<int:pk>/delete/',      admin_views.admin_report_delete,   name='admin_report_delete'),
    path('invoice/manual/',               admin_views.manual_invoice,        name='admin_manual_invoice'),
]
