from django.contrib import admin
from .models import GalleryImage, GalleryCategory


@admin.register(GalleryCategory)
class GalleryCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'is_featured', 'uploaded_at']
    list_editable = ['is_featured']
    list_filter = ['category', 'is_featured']
