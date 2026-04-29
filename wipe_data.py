import os
import django
import sys

sys.path.append('/home/rasheed/Documents/catrin_boys_website/catering_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from bookings.models import Booking
from staff.models import Staff, StaffApplication, PromotionRequest, StaffNotice, StaffAttendance, StaffPayout, FCMDevice

print("Cleaning data...")
Booking.objects.all().delete()
StaffApplication.objects.all().delete()
PromotionRequest.objects.all().delete()
StaffNotice.objects.all().delete()
StaffAttendance.objects.all().delete()
StaffPayout.objects.all().delete()
FCMDevice.objects.all().delete()

# Delete non-admin staff
non_admins = Staff.objects.filter(is_superuser=False)
non_admins.delete()

# Change admin password
admins = Staff.objects.filter(is_superuser=True)
for admin in admins:
    admin.set_password('Admin@123')
    admin.save()
    print(f"Updated password for admin: {admin.staff_id} to Admin@123")

print("Data cleanup complete!")
