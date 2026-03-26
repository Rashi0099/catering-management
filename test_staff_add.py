import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from staff.models import Staff
from staff.models import generate_staff_id

s_id = generate_staff_id()
print("Generated:", s_id)
user = Staff.objects.create_user(staff_id=s_id, password="testpassword123", full_name="Test Staff", role="chef")
print("User created successfully:", user.staff_id, user.full_name)
user.delete()
