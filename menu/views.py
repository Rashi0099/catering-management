from django.shortcuts import render, get_object_or_404
from .models import MenuCategory, MenuItem


def menu_list(request):
    """Displays the full catering menu with optional vegetarian filtering."""
    categories = MenuCategory.objects.prefetch_related('items').all()
    veg_filter = request.GET.get('veg', '')
    items = MenuItem.objects.filter(is_available=True)
    if veg_filter == 'veg':
        items = items.filter(is_vegetarian=True)
    return render(request, 'menu/menu.html', {
        'categories': categories,
        'items': items,
        'veg_filter': veg_filter,
    })


def menu_category(request, slug):
    """Displays menu items filtered by a specific category."""
    category = get_object_or_404(MenuCategory, slug=slug)
    items = category.items.filter(is_available=True)
    categories = MenuCategory.objects.all()
    return render(request, 'menu/menu.html', {
        'categories': categories,
        'active_category': category,
        'items': items,
    })
