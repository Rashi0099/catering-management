from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import TemplateView

urlpatterns = [
    path('django-admin/',  admin.site.urls),
    path('admin-panel/',   include('core.admin_urls')),   # Custom admin (owner)
    path('staff/',         include('staff.urls')),         # Staff portal
    path('',               include('core.urls')),
    path('menu/',          include('menu.urls')),
    path('bookings/',      include('bookings.urls')),
    path('gallery/',       include('gallery.urls')),
    path('webpush/',       include('webpush.urls')),
    path('firebase-messaging-sw.js', TemplateView.as_view(
        template_name="firebase-messaging-sw.js", 
        content_type="application/javascript"
    )),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
