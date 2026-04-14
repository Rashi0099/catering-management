import os
import django
from datetime import date
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from bookings.models import ManualReport

# Clear existing test data
ManualReport.objects.all().delete()

# Create dummy reports
ManualReport.objects.create(
    event_date=date(2026, 2, 10),
    site_name="Test Site 1",
    event_name="Test Event 1",
    bill_incharge="Alice"
)
ManualReport.objects.create(
    event_date=date(2026, 3, 15),
    site_name="Test Site 2",
    event_name="Test Event 2",
    bill_incharge="Bob"
)

# Test filter
print("Total reports:", ManualReport.objects.count())

month_filter = "2" # Feb
year_filter = "2026"

qs = ManualReport.objects.all()
if month_filter:
    qs = qs.filter(event_date__month=month_filter)
if year_filter:
    qs = qs.filter(event_date__year=year_filter)

print(f"Filtered for {month_filter}/{year_filter}:", qs.count())

month_filter_int = int("2")
qs2 = ManualReport.objects.all()
if month_filter:
    qs2 = qs2.filter(event_date__month=month_filter_int)

print(f"Filtered (int) for {month_filter_int}:", qs2.count())

