import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


def generate_staff_id():
    """Generates unique staff ID like CB-2024-0042"""
    year = timezone.now().year
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"CB-{year}-{suffix}"


class StaffManager(BaseUserManager):
    def create_user(self, staff_id, password, **extra):
        if not staff_id:
            raise ValueError("Staff ID is required")
        user = self.model(staff_id=staff_id, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, staff_id, password, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('role', 'admin')
        return self.create_user(staff_id, password, **extra)


class Staff(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin',    'Admin'),
        ('manager',  'Manager'),
        ('chef',     'Chef'),
        ('server',   'Server / Waiter'),
        ('driver',   'Driver'),
        ('cleaner',  'Cleaner'),
        ('other',    'Other'),
    ]

    # Login credentials
    staff_id   = models.CharField(max_length=20, unique=True, default=generate_staff_id)
    password   = models.CharField(max_length=128)  # hashed

    # Personal info
    full_name  = models.CharField(max_length=200)
    email      = models.EmailField(blank=True)
    phone      = models.CharField(max_length=20, blank=True)
    photo      = models.ImageField(upload_to='staff/', blank=True, null=True)

    # Role & pay
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='server', db_index=True)
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                     help_text="Daily wage in ₹")
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                          help_text="% of booking value as commission")

    # Status
    is_active  = models.BooleanField(default=True, db_index=True)
    is_staff   = models.BooleanField(default=False)   # can access Django admin
    joined_at  = models.DateField(auto_now_add=True)

    objects = StaffManager()

    USERNAME_FIELD  = 'staff_id'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = 'Staff Member'
        verbose_name_plural = 'Staff Members'
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.staff_id})"

    @property
    def first_name(self):
        return self.full_name.split()[0]

    def total_bookings(self):
        return self.bookings.count()

    def confirmed_bookings(self):
        return self.bookings.filter(status__in=['confirmed', 'completed']).count()

    def total_revenue_generated(self):
        from django.db.models import Sum
        result = self.bookings.filter(
            status__in=['confirmed', 'completed']
        ).aggregate(total=Sum('quoted_price'))
        return result['total'] or 0

    def total_paid_out(self):
        from django.db.models import Sum
        result = self.payouts.filter(status='paid').aggregate(total=Sum('amount'))
        return result['total'] or 0

    def pending_payout(self):
        from django.db.models import Sum
        result = self.payouts.filter(status='pending').aggregate(total=Sum('amount'))
        return result['total'] or 0


class StaffAttendance(models.Model):
    """Track which events each staff member worked"""
    STATUS = [('present', 'Present'), ('absent', 'Absent'), ('half_day', 'Half Day')]

    staff      = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='attendance')
    booking    = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE,
                                    related_name='staff_attendance', null=True, blank=True)
    date       = models.DateField(db_index=True)
    status     = models.CharField(max_length=10, choices=STATUS, default='present', db_index=True)
    hours      = models.DecimalField(max_digits=4, decimal_places=1, default=8)
    notes      = models.TextField(blank=True)

    class Meta:
        unique_together = ('staff', 'date', 'booking')
        ordering = ['-date']

    def __str__(self):
        return f"{self.staff.full_name} — {self.date} ({self.status})"


class StaffPayout(models.Model):
    """Money paid to each staff member"""
    PAYOUT_TYPE = [
        ('salary',     'Monthly Salary'),
        ('daily_wage', 'Daily Wage'),
        ('commission', 'Event Commission'),
        ('bonus',      'Bonus'),
        ('advance',    'Advance'),
    ]
    STATUS = [('pending', 'Pending'), ('paid', 'Paid'), ('cancelled', 'Cancelled')]

    staff       = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='payouts')
    booking     = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='payouts')
    payout_type = models.CharField(max_length=20, choices=PAYOUT_TYPE)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    status      = models.CharField(max_length=15, choices=STATUS, default='pending', db_index=True)
    paid_on     = models.DateField(null=True, blank=True)
    paid_by     = models.CharField(max_length=200, blank=True,
                                    help_text="Admin who approved the payment")
    reference   = models.CharField(max_length=100, blank=True,
                                    help_text="UPI ref / bank transfer ID")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"₹{self.amount} → {self.staff.full_name} ({self.get_payout_type_display()})"
