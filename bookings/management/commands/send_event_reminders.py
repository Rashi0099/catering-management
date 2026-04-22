from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime
from bookings.models import Booking
from staff.models import FCMDevice
from firebase_admin import messaging

class Command(BaseCommand):
    help = 'Sends reminder notifications to assigned staff for events happening tomorrow.'

    def handle(self, *args, **options):
        # Calculate tomorrow's date
        tomorrow = (timezone.now() + datetime.timedelta(days=1)).date()
        
        # Find bookings scheduled for tomorrow that are not cancelled
        bookings = Booking.objects.filter(event_date=tomorrow, status__in=['pending', 'confirmed'])
        
        staff_notified_count = 0
        booking_count = bookings.count()
        
        for booking in bookings:
            # Note: We rely on `assigned_to` ManyToMany field which gets populated when admin approves apps
            assigned_staff = booking.assigned_to.all()
            if not assigned_staff.exists():
                # Try fallback to approved event applications
                assigned_ids = booking.applications.filter(status='approved').values_list('staff_id', flat=True)
                tokens = list(FCMDevice.objects.filter(staff_id__in=assigned_ids).values_list('token', flat=True))
            else:
                tokens = list(FCMDevice.objects.filter(staff__in=assigned_staff).values_list('token', flat=True))

            if tokens:
                try:
                    title = "⏰ Event Reminder"
                    body = f"Reminder: You have a shift for {booking.name} tomorrow!"
                    message = messaging.MulticastMessage(
                        notification=messaging.Notification(title=title, body=body),
                        android=messaging.AndroidConfig(priority='high'),
                        webpush=messaging.WebpushConfig(
                            notification=messaging.WebpushNotification(icon="/static/images/logo.png"),
                            fcm_options=messaging.WebpushFCMOptions(link='/staff/events/')
                        ),
                        tokens=tokens,
                    )
                    messaging.send_each_for_multicast(message)
                    staff_notified_count += len(tokens)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error sending reminders for booking {booking.id}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"Successfully sent {staff_notified_count} reminders across {booking_count} events for tomorrow."))
