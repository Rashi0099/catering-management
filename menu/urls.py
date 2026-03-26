from django.urls import path
from . import views

urlpatterns = [
    path('', views.menu_list, name='menu'),
    path('<slug:slug>/', views.menu_category, name='menu_category'),
]
