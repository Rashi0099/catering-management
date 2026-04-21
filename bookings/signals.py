from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from firebase_admin import messaging

from staff.models import FCMDevice
from .models import EventApplication, Booking, EventReport
from core.utils import notify_admins


@receiver(post_save, sender=EventApplication)
def notify_staff_application_status(sender, instance, created, **kwargs):
    """Notify Staff via Web Push when their application status changes (Approved/Rejected/Cancelled)."""
    if not created:
        # Check if status has changed
        # Note: In a production environment, we'd use a dirty field tracker, 
        # but here we'll just check status against known actions.
        try:
            title = "Shift Update"
            body = f"Your application for {instance.booking.name} is now {instance.get_status_display()}."
            
            if instance.status == 'approved':
                title = "✅ Application Approved!"
                body = f"Great news! You've been approved for the {instance.booking.get_event_type_display()} on {instance.booking.event_date}."
            elif instance.status == 'rejected':
                title = "❌ Not Approved"
                body = f"Sorry, you were not selected for the {instance.booking.get_event_type_display()} on {instance.booking.event_date}."
            elif instance.status == 'cancelled':
                title = "⚠️ Shift Cancelled"
                body = f"Your shift for {instance.booking.name} has been cancelled."
            elif instance.status == 'cancel_requested':
                # Notify Admin about cancel request
                subject = f"🚩 Cancellation Request: {instance.applicant_name}"
                msg = (
                    f"{instance.applicant_name} has requested to cancel their shift for {instance.booking.name}.\n"
                    f"Event Date: {instance.booking.event_date}\n\n"
                    f"Review in Admin: /admin/bookings/eventapplication/{instance.pk}/change/"
                )
                send_mail(
                    subject, msg, settings.EMAIL_HOST_USER, 
                    [settings.EMAIL_HOST_USER], fail_silently=True
                )
                
                notify_admins(
                    title=f"🚩 Cancel Request: {instance.applicant_name}",
                    body=f"{instance.applicant_name} wants to cancel their shift for {instance.booking.name}",
                    link=f"/admin/bookings/eventapplication/{instance.pk}/change/"
                )
                return # Don't send push to user for their own request

            tokens = list(FCMDevice.objects.filter(staff=instance.staff).values_list('token', flat=True))
            if tokens:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    webpush=messaging.WebpushConfig(
                        notification=messaging.WebpushNotification(icon="/static/images/logo.png"),
                        fcm_options=messaging.WebpushFCMOptions(link='/staff/dashboard/')
                    ),
                    tokens=tokens,
                )
                try:
                    messaging.send_each_for_multicast(message)
                except Exception as e:
                    print(f"Error sending FCM multicast: {e}")
        except Exception as e:
            print(f"Notification error: {e}")


@receiver(post_save, sender=EventApplication)
def notify_admin_cancellation_request(sender, instance, created, **kwargs):
    """Handled within the status check above to avoid redundant signals, but keeping as placeholder."""
    pass

@receiver(post_save, sender=EventReport)
def notify_admin_on_report_submit(sender, instance, created, **kwargs):
    """Notify admin when a captain submits an event report."""
    if instance.status == 'submitted':
        notify_admins(
            title="📊 Captain Report Submitted",
            body=f"{instance.submitted_by.first_name} submitted a report for {instance.booking.name}.",
            link="/admin-panel/reports/events/"
        )
