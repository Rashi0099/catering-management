from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('confirmed',   'Confirmed'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]
    EVENT_TYPES = [
        ('wedding',    'Wedding'),
        ('corporate',  'Corporate Event'),
        ('birthday',   'Birthday Party'),
        ('anniversary','Anniversary'),
        ('graduation', 'Graduation'),
        ('conference', 'Conference'),
        ('other',      'Other'),
    ]
    PAYMENT_STATUS = [
        ('unpaid',   'Unpaid'),
        ('partial',  'Partial Payment'),
        ('paid',     'Fully Paid'),
        ('refunded', 'Refunded'),
    ]

    # Client
    name        = models.CharField(max_length=200)
    email       = models.EmailField()
    phone       = models.CharField(max_length=20)
    company     = models.CharField(max_length=200, blank=True)

    # Event
    event_type  = models.CharField(max_length=50, choices=EVENT_TYPES)
    session     = models.CharField(max_length=10, choices=[('day', 'Day'), ('night', 'Night')], default='day')
    event_date  = models.DateField(db_index=True)
    event_time  = models.TimeField(null=True, blank=True)
    venue       = models.CharField(max_length=300, blank=True)
    location_name = models.CharField(max_length=255, blank=True)
    location_link = models.URLField(blank=True)
    guest_count = models.IntegerField()
    budget      = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Requirements
    dietary_requirements = models.TextField(blank=True)
    special_requests     = models.TextField(blank=True)
    message              = models.TextField(blank=True)

    # Pricing
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    quoted_price   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    admin_notes    = models.TextField(blank=True)

    # Payment tracking
    payment_status  = models.CharField(max_length=15, choices=PAYMENT_STATUS, default='unpaid', db_index=True)
    amount_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_pending  = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Quotas & Visibility
    quota_captain = models.PositiveIntegerField(default=0, help_text="Number of Captains needed")
    quota_a       = models.PositiveIntegerField(default=0, help_text="Number of A-Level staff needed")
    quota_b       = models.PositiveIntegerField(default=0, help_text="Number of B-Level staff needed")
    quota_c       = models.PositiveIntegerField(default=0, help_text="Number of C-Level staff needed")
    is_long_work  = models.BooleanField(default=False, help_text="Checked if the venue is >20km from the main office")
    is_published  = models.BooleanField(default=False, help_text="If True, staff can see and apply for this event")
    allow_direct_join = models.BooleanField(default=False, help_text="If True, staff can join instantly without admin approval.")
    publish_locality = models.CharField(max_length=50, choices=[
        ('all', 'All Localities'),
        ('Kondotty', 'Kondotty'),
        ('Areekode', 'Areekode'),
        ('Edavannappara', 'Edavannappara'),
        ('Kizhisseri', 'Kizhisseri'),
        ('University', 'University'),
        ('Valluvambram', 'Valluvambram'),
    ], default='all', help_text="Publish only to staff from this locality")

    # Staff
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings_created'
    )
    assigned_to = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='bookings'
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.get_event_type_display()} on {self.event_date}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_is_published = getattr(self, 'is_published', False)
        self._original_venue = getattr(self, 'venue', '')
        self._original_event_time = getattr(self, 'event_time', None)
        self._original_guest_count = getattr(self, 'guest_count', 0)

    def save(self, *args, **kwargs):
        newly_published = getattr(self, 'is_published', False) and not self._original_is_published
        
        details_updated = False
        if self.pk and getattr(self, 'is_published', False) and not newly_published:
            if (self.venue != self._original_venue) or \
               (self.event_time != self._original_event_time) or \
               (self.guest_count != self._original_guest_count):
                details_updated = True

        super().save(*args, **kwargs)
        
        if newly_published:
            self._notify_staff_published()
        elif details_updated:
            self._notify_staff_update()
            
        self._original_is_published = getattr(self, 'is_published', False)
        self._original_venue = getattr(self, 'venue', '')
        self._original_event_time = getattr(self, 'event_time', None)
        self._original_guest_count = getattr(self, 'guest_count', 0)

    def _notify_staff_published(self):
        try:
            from firebase_admin import messaging
            from staff.models import FCMDevice, Staff
            qs = Staff.objects.filter(is_active=True)
            if self.publish_locality != 'all':
                qs = qs.filter(main_locality=self.publish_locality)
            
            tokens = list(FCMDevice.objects.filter(staff__in=qs).values_list('token', flat=True))
            if tokens:
                title = "📅 New Event Published!"
                body = f"A new {self.get_event_type_display()} event is scheduled for {self.event_date}. Apply now!"
                message = messaging.MulticastMessage(
                    data={
                        'title': str(title),
                        'body': str(body),
                        'link': '/staff/events/',
                        'icon': '/static/images/logo.png'
                    },
                    tokens=tokens,
                )
                messaging.send_each_for_multicast(message)
        except Exception as e:
            print(f"FCM Publication Notify error: {e}")

    def _notify_staff_update(self):
        try:
            from firebase_admin import messaging
            from staff.models import FCMDevice
            
            assigned_ids = self.applications.filter(status='approved').values_list('staff_id', flat=True)
            tokens = list(FCMDevice.objects.filter(staff_id__in=assigned_ids).values_list('token', flat=True))
            if not tokens:
                tokens = list(FCMDevice.objects.filter(staff__in=self.assigned_to.all()).values_list('token', flat=True))
                
            if tokens:
                title = "⚠️ Event Update"
                body = f"Details for {self.name} have changed. Check the new timings or venue!"
                message = messaging.MulticastMessage(
                    data={
                        'title': str(title),
                        'body': str(body),
                        'link': '/staff/dashboard/',
                        'icon': '/static/images/logo.png'
                    },
                    tokens=tokens,
                )
                messaging.send_each_for_multicast(message)
        except Exception as e:
            print(f"FCM Update Notify error: {e}")

    @property
    def balance_due(self):
        if self.quoted_price:
            return self.quoted_price - self.amount_received
        return 0

    @property
    def is_cancellable(self):
        from django.utils import timezone
        import datetime
        event_time = self.event_time or datetime.time(0, 0)
        dt = datetime.datetime.combine(self.event_date, event_time)
        
        if timezone.is_aware(timezone.now()):
            event_dt = timezone.make_aware(dt, timezone.get_current_timezone())
        else:
            event_dt = dt
            
        return event_dt > (timezone.now() + datetime.timedelta(hours=24))

    def generate_default_tasks(self):
        if self.tasks.exists():
            return
            
        default_tasks = [
            {"name": "STAFF & ATTANDANCE", "desc": ""},
            {"name": "MENU REVIEW", "desc": ""},
            {"name": "GUEST COUNT & PLANNING", "desc": ""},
            {"name": "EQUIPMENT & VESSEL CHECK", "desc": ""},
            {"name": "Plate", "desc": "Used plate and plate"},
            {"name": "Bottle", "desc": ""},
            {"name": "Disposable items verification", "desc": ""},
            {"name": "Courter setup and arrangement", "desc": ""},
            {"name": "Hygiene and safety check", "desc": "Ensure all staff follow hygiene standards. Check handwashing areas and waste disposal system. Maintain cleanliness throughout the event."},
            {"name": "Closing responsibility", "desc": ""}
        ]
        
        from .models import EventTask
        for task in default_tasks:
            EventTask.objects.create(booking=self, task_name=task["name"], description=task["desc"])


class BookingPayment(models.Model):
    METHOD_CHOICES = [
        ('cash',   'Cash'),
        ('upi',    'UPI / GPay / PhonePe'),
        ('bank',   'Bank Transfer'),
        ('card',   'Card'),
        ('cheque', 'Cheque'),
    ]

    booking     = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    method      = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference   = models.CharField(max_length=200, blank=True)
    received_on = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='payments_received'
    )
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_on']

    def __str__(self):
        return f"Rs.{self.amount} for {self.booking.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._recalc_booking_totals()

    def delete(self, *args, **kwargs):
        booking = self.booking  # Hold reference before deletion
        super().delete(*args, **kwargs)
        self._recalc_booking_totals_for(booking)

    def _recalc_booking_totals(self):
        self._recalc_booking_totals_for(self.booking)

    @staticmethod
    def _recalc_booking_totals_for(booking):
        from django.db.models import Sum
        total = booking.payments.aggregate(t=Sum('amount'))['t'] or 0
        booking.amount_received = total
        if booking.quoted_price:
            booking.amount_pending = booking.quoted_price - total
            if total >= booking.quoted_price:
                booking.payment_status = 'paid'
            elif total > 0:
                booking.payment_status = 'partial'
            else:
                booking.payment_status = 'unpaid'
        else:
            booking.amount_pending = 0
            booking.payment_status = 'unpaid' if total == 0 else 'partial'
        booking.save(update_fields=['amount_received', 'amount_pending', 'payment_status'])


class Testimonial(models.Model):
    client_name = models.CharField(max_length=200)
    event_type  = models.CharField(max_length=100)
    rating      = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    review      = models.TextField()
    is_featured = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client_name} — {self.rating}*"


class EventApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Not Approved'),
        ('cancel_requested', 'Cancel Requested'),
        ('cancelled', 'Cancelled')
    ]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='applications')
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_applications')
    applicant_name = models.CharField(max_length=200)
    applicant_phone = models.CharField(max_length=20)
    note = models.TextField(blank=True, help_text="Note from staff to admin")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    cancel_rejected = models.BooleanField(default=False, help_text="True if admin denied a cancel request")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('booking', 'staff')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.applicant_name} for {self.booking.name} ({self.get_status_display()})"


class ManualReport(models.Model):
    """
    Dedicated table for standalone manual financial reporting.
    This is entirely disconnected from system logic, allowing the Admin
    to manually log details matching their legacy spreadsheet workflows.
    """
    event_date = models.DateField()
    site_name = models.CharField(max_length=255)
    event_name = models.CharField(max_length=255)
    boys_count = models.IntegerField(default=0)
    bill_incharge = models.CharField(max_length=255)
    bill_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_received_on = models.DateField(null=True, blank=True)
    pending_amount = models.CharField(max_length=255, blank=True, null=True, help_text="Can be NIL or numeric")
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_settled = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-created_at']

    def __str__(self):
        return f"Report: {self.event_name} on {self.event_date}"


class EventReport(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='reports')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submitted_reports')
    
    # Financials & Metrics
    status = models.CharField(max_length=20, choices=[('draft', 'Draft'), ('submitted', 'Submitted')], default='draft')
    bill_in_charge = models.CharField(max_length=255, default='NIL', blank=True)
    total_amount   = models.CharField(max_length=255, default='NIL', blank=True)
    balance_amount = models.CharField(max_length=255, default='NIL', blank=True)
    pending        = models.CharField(max_length=255, default='NIL', blank=True)
    
    # Logistics
    juice         = models.CharField(max_length=255, default='NIL', blank=True)
    tea           = models.CharField(max_length=255, default='NIL', blank=True)
    popcorn       = models.CharField(max_length=255, default='NIL', blank=True)
    hosting       = models.CharField(max_length=255, default='NIL', blank=True)
    coat_incharge = models.CharField(max_length=255, default='NIL', blank=True)
    coat_rent     = models.CharField(max_length=255, default='NIL', blank=True)
    ta            = models.CharField(max_length=255, default='NIL', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Report for {self.booking.name} by {self.submitted_by.full_name}"


class EventTask(models.Model):
    """
    Checklist for Captain responsibilities at an event.
    Standard tasks are generated automatically per booking.
    """
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='tasks')
    task_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey('staff.Staff', null=True, blank=True, on_delete=models.SET_NULL, related_name='completed_tasks')
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"[{'X' if self.is_completed else ' '}] {self.task_name} - {self.booking}"


@receiver([post_save, post_delete], sender=Booking)
def invalidate_booking_caches(sender, instance, **kwargs):
    """Clear admin counters when bookings are created, updated, or deleted."""
    cache.delete('pending_booking_count')
    cache.delete('admin_dashboard_stats')
