import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')

import django
django.setup()

from django.template.loader import get_template
from django.conf import settings

errors = []
for root, _, files in os.walk(os.path.join(settings.BASE_DIR, 'templates')):
    for f in files:
        if f.endswith('.html'):
            try:
                get_template(os.path.relpath(os.path.join(root, f), os.path.join(settings.BASE_DIR, 'templates')))
            except Exception as e:
                errors.append(f"{f}: {e}")

if errors:
    print("ERRORS:")
    for e in errors:
        print(e)
else:
    print("ALL TEMPLATES RENDER OK")
