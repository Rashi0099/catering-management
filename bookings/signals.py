from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
try:
    from webpush import send_user_notification
except ImportError:
    send_user_notification = None

from .models import EventApplication, Booking

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
                return # Don't send push to user for their own request

            payload = {
                "head": title,
                "body": body,
                "icon": "/static/images/logo.png",
                "url": "/staff/dashboard/"
            }
            send_user_notification(user=instance.staff, payload=payload, ttl=3600)
        except ImportError:
            pass

@receiver(post_save, sender=EventApplication)
def notify_admin_cancellation_request(sender, instance, created, **kwargs):
    """Handled within the status check above to avoid redundant signals, but keeping as placeholder."""
    pass
