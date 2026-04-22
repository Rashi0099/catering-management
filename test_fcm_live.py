import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from staff.models import FCMDevice, Staff
from core.utils import send_fcm_notification
from firebase_admin import messaging

devices = FCMDevice.objects.all()
print(f"Total FCM Devices in DB: {devices.count()}")
for d in devices:
    print(f"- Staff: {d.staff.full_name}, Token preview: {d.token[:20]}..., Created: {d.created_at}")

staff_users = Staff.objects.filter(fcm_devices__isnull=False).distinct()
print(f"\nSending test notification to {staff_users.count()} staff members...")

for staff in staff_users:
    response = send_fcm_notification(staff, "Admin Test", "This is a direct API test")
    if response:
        print(f"Sent to {staff.full_name}: Successes: {response.success_count}, Failures: {response.failure_count}")
        for idx, res in enumerate(response.responses):
            if res.success:
                print(f"  Token {idx} -> Success: message_id {res.message_id}")
            else:
                print(f"  Token {idx} -> Failed: {res.exception}")
    else:
        print(f"Failed to even call send_fcm_notification for {staff.full_name}")

print("\n--- Current FCM Tokens after cleanup ---")
for d in FCMDevice.objects.all():
    print(f"- Staff: {d.staff.full_name}, Token preview: {d.token[:20]}...")
