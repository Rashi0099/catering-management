from django.db.models.signals import post_save, post_init
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from .models import EventApplication, EventReport
from core.utils import notify_admins


# ── Track original status so we only fire on real changes ────────────────────
@receiver(post_init, sender=EventApplication)
def track_application_original_status(sender, instance, **kwargs):
    """Store original status right after the object is loaded from DB."""
    instance._original_status = getattr(instance, 'status', 'pending')


@receiver(post_save, sender=EventApplication)
def notify_staff_application_status(sender, instance, created, **kwargs):
    """Notify Staff via Web Push ONLY when their application status actually changes."""
    if not created:
        # Only fire if status changed from what it was when loaded from DB
        original = getattr(instance, '_original_status', None)
        if original == instance.status:
            return  # Status did not change — skip notification entirely
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

            from core.utils import send_fcm_notification
            send_fcm_notification(instance.staff, title, body, link='/staff/dashboard/')

        except Exception as e:
            print(f"Notification error: {e}")


# NOTE: cancel_requested logic is fully handled inside notify_staff_application_status above.
# The empty function below was removed to avoid unnecessary signal handler registration.

@receiver(post_save, sender=EventReport)
def notify_admin_on_report_submit(sender, instance, created, **kwargs):
    """Notify admin ONLY when a report transitions TO 'submitted' (not on every draft save)."""
    # Only notify on explicit status field update to 'submitted', not on draft resaves
    update_fields = kwargs.get('update_fields') or []
    status_just_saved = not update_fields or 'status' in update_fields
    if instance.status == 'submitted' and status_just_saved and not created:
        notify_admins(
            title="📊 Captain Report Submitted",
            body=f"{instance.submitted_by.first_name} submitted a report for {instance.booking.name}.",
            link="/admin-panel/reports/events/"
        )
