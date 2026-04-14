import os
import django
import urllib.request
import sys

# Setup django
sys.path.append('/home/rasheed/Documents/catrin_boys_website/catering_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from menu.models import MenuCategory, MenuItem
from gallery.models import GalleryCategory, GalleryImage
from django.core.files import File

# Image URLs (using loremflickr which provides random images for keywords)
MENU_IMAGES = [
    ("Chicken Biryani", "Delicious Malabar Chicken Biryani", 180.00, "https://loremflickr.com/800/600/biryani"),
    ("Kerala Sadhya", "Traditional sadhya served on banana leaf", 250.00, "https://loremflickr.com/800/600/sadhya,food"),
    ("Pal Payasam", "Sweet milk dessert with cashews", 80.00, "https://loremflickr.com/800/600/dessert"),
]

GALLERY_IMAGES = [
    ("Wedding Buffet Setup", "https://loremflickr.com/800/600/buffet,wedding"),
    ("Chefs Preparing Food", "https://loremflickr.com/800/600/chef,cooking"),
    ("Outdoor Dining Arrangement", "https://loremflickr.com/800/600/dining,outdoor,catering"),
]

def download_image(url, filename):
    filepath, _ = urllib.request.urlretrieve(url, filename)
    return filepath

def populate():
    print("Setting up Categories...")
    menu_cat, _ = MenuCategory.objects.get_or_create(name="Main Course", defaults={"icon": "🍛", "order": 1})
    gallery_cat, _ = GalleryCategory.objects.get_or_create(name="Events")

    print("Populating Menu Items...")
    for name, desc, price, url in MENU_IMAGES:
        if not MenuItem.objects.filter(name=name).exists():
            print(f"Downloading image for {name}...")
            temp_path = download_image(url, f"/tmp/{name.replace(' ', '_')}.jpg")
            item = MenuItem(
                category=menu_cat,
                name=name,
                description=desc,
                price=price,
                is_featured=True
            )
            with open(temp_path, 'rb') as f:
                # Assign image using Django's File wrapper
                item.image.save(f"{name.replace(' ', '_')}.jpg", File(f), save=True)
            print(f"Added {name}")

    print("Populating Gallery Images...")
    for title, url in GALLERY_IMAGES:
        if not GalleryImage.objects.filter(title=title).exists():
            print(f"Downloading image for {title}...")
            temp_path = download_image(url, f"/tmp/{title.replace(' ', '_')}.jpg")
            img = GalleryImage(
                category=gallery_cat,
                title=title,
                is_featured=True
            )
            with open(temp_path, 'rb') as f:
                img.image.save(f"{title.replace(' ', '_')}.jpg", File(f), save=True)
            print(f"Added {title}")

    print("Done!")

if __name__ == '__main__':
    populate()
