from django.urls import path
from django.views.generic import TemplateView, RedirectView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('booking/', RedirectView.as_view(url='/bookings/', permanent=True)),
    path('contact/', views.contact, name='contact'),
    
    # PWA Endpoints
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw.js'),
    path('manifest.json', views.manifest, name='manifest.json'),
]
