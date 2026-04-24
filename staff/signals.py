from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from .models import StaffNotice, StaffApplication, PromotionRequest
from core.utils import notify_admins

@receiver(post_save, sender=StaffApplication)
def notify_admin_new_application(sender, instance, created, **kwargs):
    """Notify Admin via Email when a new staff application is received."""
    if created:
        subject = f"🆕 New Staff Application: {instance.full_name}"
        message = (
            f"A new staff application has been received.\n\n"
            f"Name: {instance.full_name}\n"
            f"Phone: {instance.phone_1}\n"
            f"Locality: {instance.main_locality}\n"
            f"Age: {instance.age}\n\n"
            f"Review in Admin: /admin/staff/staffapplication/{instance.pk}/change/"
        )
        send_mail(
            subject, message, settings.EMAIL_HOST_USER, 
            [settings.EMAIL_HOST_USER], fail_silently=True
        )

@receiver(post_save, sender=PromotionRequest)
def notify_admin_promotion_request(sender, instance, created, **kwargs):
    """Notify Admin via Email when a staff member requests a promotion."""
    if created:
        subject = f"📈 Promotion Request: {instance.staff.full_name}"
        message = (
            f"{instance.staff.full_name} has requested a promotion.\n"
            f"Current Level: {instance.current_level}\n"
            f"Requested Level: {instance.requested_level}\n\n"
            f"Review in Admin: /admin/staff/promotionrequest/{instance.pk}/change/"
        )
        send_mail(
            subject, message, settings.EMAIL_HOST_USER, 
            [settings.EMAIL_HOST_USER], fail_silently=True
        )



@receiver(post_save, sender=StaffApplication)
def notify_admin_on_staff_application(sender, instance, created, **kwargs):
    if created:
        notify_admins(
            title="👤 New Staff Application",
            body=f"{instance.full_name} applied to join the team from {instance.place}.",
            link="/admin-panel/staff/applications/"
        )

@receiver(post_save, sender=PromotionRequest)
def notify_admin_on_promotion_request(sender, instance, created, **kwargs):
    if created:
        notify_admins(
            title="⭐ Promotion Request",
            body=f"{instance.staff.first_name} wants to upgrade from {instance.get_current_level_display()} to {instance.get_requested_level_display()}.",
            link="/admin-panel/staff/promotions/"
        )

@receiver(post_save, sender=StaffNotice)
def notify_staff_new_notice(sender, instance, created, **kwargs):
    """Notify all active staff when an active notice is posted/updated"""
    if instance.is_active:
        from core.utils import notify_all_staff_background
        title = "📢 New Notice" if created else "📢 Notice Updated"
        body = instance.message[:100] + ('...' if len(instance.message) > 100 else '')
        notify_all_staff_background(title=title, body=body, link="/staff/dashboard/")
