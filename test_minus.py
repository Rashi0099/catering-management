import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_project.settings')
django.setup()

from bookings.models import ManualReport
import datetime

try:
    report = ManualReport.objects.create(
        event_date=datetime.date.today(),
        site_name="Test Site",
        event_name="Test Event",
        profit="-500.50"
    )
    print("SUCCESS: Negative profit saved.")
    report.delete()
except Exception as e:
    print(f"ERROR: {str(e)}")
