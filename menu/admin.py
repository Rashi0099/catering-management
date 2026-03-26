from django.contrib import admin
from .models import MenuCategory, MenuItem


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'icon', 'order']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_vegetarian', 'is_available', 'is_featured']
    list_filter = ['category', 'is_vegetarian', 'is_available', 'is_featured']
    list_editable = ['price', 'is_available', 'is_featured']
    search_fields = ['name', 'description']
