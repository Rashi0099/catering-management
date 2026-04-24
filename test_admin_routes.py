import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from django.test import Client
from staff.models import Staff
from bookings.models import Booking

client = Client()
admin = Staff.objects.filter(is_superuser=True).first()
client.force_login(admin)

urls = [
    '/admin-panel/',
    '/admin-panel/bookings/',
    '/admin-panel/staff/applications/',
    '/admin-panel/staff/promotions/',
    '/admin-panel/notices/'
]

booking = Booking.objects.first()
if booking:
    urls.append(f'/admin-panel/bookings/{booking.pk}/')

for url in urls:
    try:
        response = client.get(url)
        print(f"URL: {url} -> {response.status_code}")
        if response.status_code == 500:
            print(f"Error on {url}:")
            print(response.content[-1000:]) # print part of the traceback
    except Exception as e:
        print(f"Exception on {url} -> {e}")

