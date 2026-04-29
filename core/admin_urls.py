from django.urls import path
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView
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
    path('bookings/<int:pk>/ajax-update/', admin_views.admin_ajax_update_booking_field, name='admin_ajax_update_booking_field'),
    path('bookings/<int:pk>/quick-update-quota/', admin_views.admin_quick_update_quota, name='admin_quick_update_quota'),
    path('bookings/<int:pk>/attendance/ajax-update/', admin_views.admin_ajax_update_attendance_field, name='admin_ajax_update_attendance_field'),
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
    path('reports/pdf/',                  admin_views.admin_reports_pdf,     name='admin_reports_pdf'),
    path('reports/event-reports/',        admin_views.event_reports_list,    name='admin_event_reports'),
    path('reports/event-reports/<int:pk>/', admin_views.event_report_detail,  name='admin_event_report_detail'),
    path('reports/add/',                  admin_views.admin_report_add,      name='admin_report_add'),
    path('reports/<int:pk>/edit/',        admin_views.admin_report_edit,     name='admin_report_edit'),
    path('reports/<int:pk>/delete/',      admin_views.admin_report_delete,   name='admin_report_delete'),
    path('invoice/manual/',               admin_views.manual_invoice,           name='admin_manual_invoice'),
    path('invoice/download/',             admin_views.download_invoice_pdf,     name='admin_download_invoice_pdf'),
    path('invoice/history/',              admin_views.invoice_history,          name='admin_invoice_history'),
    path('invoice/history/<int:pk>/download/', admin_views.invoice_history_download, name='admin_invoice_history_download'),
    path('invoice/history/<int:pk>/delete/', admin_views.invoice_history_delete, name='admin_invoice_history_delete'),
    path('api/clients/',                  admin_views.api_get_clients,          name='admin_api_clients'),

    # Notepad
    path('notepad/',                      admin_views.notepad,                  name='admin_notepad'),
    path('notepad/category/add/',         admin_views.note_category_add,        name='admin_note_category_add'),
    path('notepad/<int:pk>/save/',        admin_views.note_save,                name='admin_note_save'),
    path('notepad/<int:pk>/delete/',      admin_views.note_delete,              name='admin_note_delete'),

    # Settings
    path('settings/', admin_views.admin_settings, name='admin_settings'),
    
    # Locality Settings
    path('settings/localities/', admin_views.locality_list, name='admin_locality_list'),
    path('settings/localities/add/',              admin_views.locality_add,         name='admin_locality_add'),
    path('settings/localities/<int:pk>/edit/',    admin_views.locality_edit,        name='admin_locality_edit'),
    path('settings/localities/<int:pk>/delete/',  admin_views.locality_delete,      name='admin_locality_delete'),
    
    path('settings/clients/',                     admin_views.client_list,          name='admin_client_list'),
    path('settings/clients/add/',                 admin_views.client_add,           name='admin_client_add'),
    path('settings/clients/<int:pk>/edit/',       admin_views.client_edit,          name='admin_client_edit'),
    path('settings/clients/<int:pk>/delete/',     admin_views.client_delete,        name='admin_client_delete'),

    # Terms & Conditions Settings
    path('settings/terms/',                        admin_views.terms_list,           name='admin_terms_list'),
    path('settings/terms/add/',                    admin_views.term_add,             name='admin_term_add'),
    path('settings/terms/<int:pk>/edit/',          admin_views.term_edit,            name='admin_term_edit'),
    path('settings/terms/<int:pk>/delete/',        admin_views.term_delete,          name='admin_term_delete'),

    # Invoice Items Settings
    path('settings/invoice-items/',                admin_views.invoice_items_list,   name='admin_invoice_items_list'),
    path('settings/invoice-items/add/',            admin_views.invoice_item_add,     name='admin_invoice_item_add'),
    path('settings/invoice-items/<int:pk>/edit/',  admin_views.invoice_item_edit,    name='admin_invoice_item_edit'),
    path('settings/invoice-items/<int:pk>/delete/',admin_views.invoice_item_delete,  name='admin_invoice_item_delete'),

    # API
    path('api/invoice-items/',                     admin_views.api_get_invoice_items, name='admin_api_invoice_items'),

    # Admin PWA manifest
    path('manifest.json',
         cache_control(no_cache=True, must_revalidate=True)(
             TemplateView.as_view(
                 template_name='admin/manifest.json',
                 content_type='application/json'
             )
         ),
         name='admin_manifest'),
]
