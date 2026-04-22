from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from firebase_admin import messaging

from .models import Staff, FCMDevice, StaffNotice, StaffApplication, PromotionRequest
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

@receiver(post_save, sender=StaffNotice)
def broadcast_notice_to_staff(sender, instance, created, **kwargs):
    """Send FCM Web Push to all active staff when a new notice is published."""
    if instance.is_active:
        tokens = list(FCMDevice.objects.filter(staff__is_active=True).values_list('token', flat=True))
        if tokens:
            body_text = instance.message[:100] + ("..." if len(instance.message) > 100 else "")
            title = "📢 New Staff Notice"
            icon = "/static/images/logo.png"
            message = messaging.MulticastMessage(
                # notification field — triggers OS-level display on Android when Chrome is killed
                notification=messaging.Notification(title=title, body=body_text),
                # data field — lets the service worker 'push' handler read title/body correctly
                data={
                    'title': title,
                    'body': body_text,
                    'link': '/staff/',
                    'icon': icon,
                },
                # High priority — ensures delivery even when device is in Doze mode
                android=messaging.AndroidConfig(priority='high'),
                webpush=messaging.WebpushConfig(
                    headers={"Urgency": "high"},
                    notification=messaging.WebpushNotification(
                        icon=icon,
                        title=title,
                        body=body_text,
                    ),
                    fcm_options=messaging.WebpushFCMOptions(link='/staff/')
                ),
                tokens=tokens,
            )
            try:
                response = messaging.send_each_for_multicast(message)
                # Clean up stale/expired tokens to keep the device table healthy
                if response.failure_count > 0:
                    stale_tokens = [
                        tokens[i] for i, r in enumerate(response.responses) if not r.success
                    ]
                    if stale_tokens:
                        FCMDevice.objects.filter(token__in=stale_tokens).delete()
            except Exception as e:
                print(f"Error sending FCM multicast: {e}")

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
