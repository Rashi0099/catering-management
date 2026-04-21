from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from firebase_admin import messaging

from .models import StaffApplication, PromotionRequest, StaffNotice, Staff, FCMDevice

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

@receiver(post_save, sender=StaffNotice)
def broadcast_notice_to_staff(sender, instance, created, **kwargs):
    """Send FCM Web Push to all active staff when a new notice is published."""
    if created and instance.is_active:
        tokens = list(FCMDevice.objects.filter(staff__is_active=True).values_list('token', flat=True))
        if tokens:
            body_text = instance.message[:100] + ("..." if len(instance.message) > 100 else "")
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title="📢 New Staff Notice",
                    body=body_text,
                ),
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(icon="/static/images/logo.png"),
                    fcm_options=messaging.WebpushFCMOptions(link='/staff/')
                ),
                tokens=tokens,
            )
            try:
                messaging.send_each_for_multicast(message)
            except Exception as e:
                print(f"Error sending FCM multicast: {e}")
