from django.urls import path
from django.views.generic import TemplateView, RedirectView
from django.views.decorators.cache import cache_control
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('booking/', RedirectView.as_view(url='/bookings/', permanent=True)),
    path('contact/', views.contact, name='contact'),
    
    # PWA Endpoints
    path('sw.js', cache_control(no_cache=True, must_revalidate=True, max_age=0)(TemplateView.as_view(template_name='sw.js', content_type='application/javascript')), name='sw.js'),
    path('manifest.json', views.manifest, name='manifest.json'),
    path('offline/', TemplateView.as_view(template_name='core/offline.html'), name='offline'),
    path('download/', views.download_app, name='download_app'),

    # TWA: Digital Asset Links — required for Android to trust the APK for mastan.in
    path('.well-known/assetlinks.json',
         cache_control(no_cache=True, must_revalidate=True)(
             TemplateView.as_view(
                 template_name='assetlinks.json',
                 content_type='application/json'
             )
         ),
         name='assetlinks'),
]

