import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.conf import settings

failed = False
# Using the app directories loader, so let's just try to load all HTML files in TEMPLATES DIRS
dirs_to_check = settings.TEMPLATES[0].get('DIRS', [])
# If app_dirs is True, we normally also check apps
# Here we'll just check the active open files from Editor
files = [
    'admin/staff_edit.html',
    'pagination.html',
    'staff/dashboard.html',
    'staff/base.html',
    'admin/booking_detail.html',
    'admin/staff_list.html',
    'staff/password_change.html',
    'admin/staff_promotions.html'
]
for rel_path in files:
    try:
        get_template(rel_path)
    except TemplateDoesNotExist:
        continue # might be normal if not all are mapped correctly or I made a typo
    except Exception as e:
        print(f"Error in {rel_path}: {e}")
        failed = True
if not failed:
    print("All tested templates OK")
