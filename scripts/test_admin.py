import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from django.contrib.admin.sites import site
from staff.admin import StaffAdmin
from staff.models import Staff

staff_admin = StaffAdmin(Staff, site)
print("Add Form:", staff_admin.add_form)
try:
    form = staff_admin.add_form()
    print("Form initialized successfully.")
    print("Fields:", form.fields.keys())
except Exception as e:
    print("Error initializing form:", type(e).__name__, "-", str(e))
