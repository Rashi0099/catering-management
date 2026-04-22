from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import TemplateView
from django.views.decorators.cache import cache_control

urlpatterns = [
    path('django-admin/',  admin.site.urls),
    path('admin-panel/',   include('core.admin_urls')),   # Custom admin (owner)
    path('staff/',         include('staff.urls')),         # Staff portal
    path('',               include('core.urls')),
    path('menu/',          include('menu.urls')),
    path('bookings/',      include('bookings.urls')),
    path('gallery/',       include('gallery.urls')),
    path('firebase-messaging-sw.js', cache_control(no_cache=True, must_revalidate=True, max_age=0)(TemplateView.as_view(
        template_name="firebase-messaging-sw.js", 
        content_type="application/javascript"
    ))),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
