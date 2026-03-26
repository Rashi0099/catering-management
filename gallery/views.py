from django.shortcuts import render
from .models import GalleryImage, GalleryCategory


def gallery(request):
    categories = GalleryCategory.objects.all()
    cat_filter = request.GET.get('cat', '')
    images = GalleryImage.objects.all()
    if cat_filter:
        images = images.filter(category__id=cat_filter)
    return render(request, 'gallery/gallery.html', {
        'images': images,
        'categories': categories,
        'cat_filter': cat_filter,
    })
