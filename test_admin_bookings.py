import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from django.test import Client
from staff.models import Staff

client = Client()
# Need an admin
admin = Staff.objects.filter(is_superuser=True).first()
if not admin:
    admin = Staff.objects.create_superuser('testadmin', 'test@test.com', 'testpass')

client.force_login(admin)
response = client.get('/admin-panel/bookings/')
print(f"Status Code: {response.status_code}")
if response.status_code == 500:
    print(response.content)

