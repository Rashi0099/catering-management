from django.db import models
from django.conf import settings


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('confirmed',   'Confirmed'),
        ('in_progress', 'In Progress'),
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
    event_date  = models.DateField(db_index=True)
    event_time  = models.TimeField(null=True, blank=True)
    venue       = models.CharField(max_length=300, blank=True)
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

    # Staff
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings_created'
    )
    assigned_to = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='bookings'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.get_event_type_display()} on {self.event_date}"

    @property
    def balance_due(self):
        if self.quoted_price:
            return self.quoted_price - self.amount_received
        return 0


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
        from django.db.models import Sum
        total = self.booking.payments.aggregate(t=Sum('amount'))['t'] or 0
        self.booking.amount_received = total
        if self.booking.quoted_price:
            self.booking.amount_pending = self.booking.quoted_price - total
            if total >= self.booking.quoted_price:
                self.booking.payment_status = 'paid'
            elif total > 0:
                self.booking.payment_status = 'partial'
        self.booking.save(update_fields=['amount_received', 'amount_pending', 'payment_status'])


class Testimonial(models.Model):
    client_name = models.CharField(max_length=200)
    event_type  = models.CharField(max_length=100)
    rating      = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    review      = models.TextField()
    is_featured = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client_name} — {self.rating}*"
