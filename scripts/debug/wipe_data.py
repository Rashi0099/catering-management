"""
Debug Utility: Wipe all booking/staff data and reset admin password.
⚠️  WARNING: This DELETES all bookings, staff applications, payouts, etc.
⚠️  NEVER run this on production. Dev/staging only.
Usage: python scripts/debug/wipe_data.py
"""
import os
import sys
import django

# Auto-detect project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from bookings.models import Booking
from staff.models import Staff, StaffApplication, PromotionRequest, StaffNotice, StaffAttendance, StaffPayout, FCMDevice

confirm = input("⚠️  This will DELETE all data. Type 'YES' to confirm: ")
if confirm != 'YES':
    print("Aborted.")
    sys.exit(0)

print("Cleaning data...")
Booking.objects.all().delete()
StaffApplication.objects.all().delete()
PromotionRequest.objects.all().delete()
StaffNotice.objects.all().delete()
StaffAttendance.objects.all().delete()
StaffPayout.objects.all().delete()
FCMDevice.objects.all().delete()

# Delete non-admin staff
Staff.objects.filter(is_superuser=False).delete()

# Reset admin passwords
new_password = input("Enter new admin password (leave blank to skip): ").strip()
if new_password:
    for admin in Staff.objects.filter(is_superuser=True):
        admin.set_password(new_password)
        admin.save()
        print(f"  ✅ Reset password for: {admin.staff_id}")

print("Data cleanup complete!")
