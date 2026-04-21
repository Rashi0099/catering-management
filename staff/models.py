import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


def generate_staff_id():
    """Generates unique staff ID like MS-0001 sequentially with numeric logic"""
    from staff.models import Staff
    from django.db.utils import ProgrammingError, OperationalError
    
    try:
        # Fetch all MS- IDs and find the numeric maximum
        ms_ids = Staff.objects.filter(staff_id__startswith='MS-').values_list('staff_id', flat=True)
        max_num = 0
        for sid in ms_ids:
            try:
                # Extract number from 'MS-XXXX'
                num = int(sid.split('-')[1])
                if num > max_num:
                    max_num = num
            except (IndexError, ValueError):
                continue
        
        new_num = max_num + 1
        
        # Collision check loop
        while True:
            generated_id = f"MS-{new_num:04d}"
            if not Staff.objects.filter(staff_id=generated_id).exists():
                return generated_id
            new_num += 1
            
    except (ProgrammingError, OperationalError):
        # Fallback for fresh DBs or migration issues
        return f"MS-{random.randint(1000, 9999)}"


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
        extra.setdefault('level', 'admin')
        return self.create_user(staff_id, password, **extra)


class Staff(AbstractBaseUser, PermissionsMixin):
    LEVEL_CHOICES = [
        ('A', 'A Level'),
        ('B', 'B Level'),
        ('C', 'C Level'),
        ('captain', 'Captain'),
        ('admin', 'Admin'),
    ]

    # Login credentials
    staff_id   = models.CharField(max_length=20, unique=True, default=generate_staff_id)
    password   = models.CharField(max_length=128)  # hashed

    # Personal info
    full_name  = models.CharField(max_length=200)
    email      = models.EmailField(blank=True)
    phone      = models.CharField(max_length=20, blank=True)
    phone_2    = models.CharField(max_length=20, blank=True)
    photo      = models.ImageField(upload_to='staff/', blank=True, null=True)

    # Detailed Profiling
    COAT_SIZE_CHOICES = [
        ('S', 'Small (S)'),
        ('M', 'Medium (M)'),
        ('L', 'Large (L)'),
        ('XL', 'Extra Large (XL)'),
        ('XXL', 'Double XL (XXL)'),
    ]
    LOCALITY_CHOICES = [
        ('Kondotty', 'Kondotty'),
        ('Areekode', 'Areekode'),
        ('Edavannappara', 'Edavannappara'),
        ('Kizhisseri', 'Kizhisseri'),
        ('University', 'University'),
        ('Valluvambram', 'Valluvambram'),
    ]
    main_locality = models.CharField(max_length=50, choices=LOCALITY_CHOICES, blank=True, null=True, help_text="Major operational area")
    coat_size = models.CharField(max_length=5, choices=COAT_SIZE_CHOICES, blank=True, null=True, help_text="Required coat size")

    age = models.PositiveIntegerField(null=True, blank=True)
    height = models.CharField(max_length=20, blank=True)
    blood_group = models.CharField(max_length=10, blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    place = models.CharField(max_length=255, blank=True, help_text="Specific city/town details")
    education = models.CharField(max_length=255, blank=True)
    aadhar_card_no = models.CharField(max_length=20, blank=True)

    # Role & pay
    level      = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='C', db_index=True)
    total_events_completed = models.PositiveIntegerField(default=0)
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                     help_text="Daily wage in ₹")
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                          help_text="% of booking value as commission")

    # Status
    is_active  = models.BooleanField(default=True, db_index=True)
    is_staff   = models.BooleanField(default=False)   # can access Django admin
    must_change_password = models.BooleanField(default=False,
        help_text="Force this staff member to change their password on next login.")
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

    def get_working_duration(self):
        from django.utils import timezone
        diff = timezone.now().date() - self.joined_at
        days = diff.days
        years = days // 365
        months = (days % 365) // 30
        parts = []
        if years > 0:
            parts.append(f"{years} yr{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} mo{'s' if months > 1 else ''}")
        if not parts:
            return "< 1 mo"
        return " ".join(parts)

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
    STATUS = [('present', 'Present'), ('absent', 'Absent')]

    staff      = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='attendance')
    booking    = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE,
                                    related_name='staff_attendance', null=True, blank=True)
    date       = models.DateField(db_index=True)
    status     = models.CharField(max_length=10, choices=STATUS, default='present', db_index=True)
    reaching_time = models.TimeField(null=True, blank=True)
    on_time    = models.BooleanField(default=True)
    shoes      = models.BooleanField(default=True)
    uniform    = models.BooleanField(default=True)
    grooming   = models.BooleanField(default=True)
    hours      = models.DecimalField(max_digits=4, decimal_places=1, default=8)
    payment_given = models.BooleanField(default=False)

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


class StaffApplication(models.Model):
    """Stores applications for staff roles from the website"""
    STATUS_CHOICES = [
        ('unverified', 'Unverified Phone'),
        ('pending', 'Pending Admin Review'),
        ('approved', 'Approved'),
        ('rejected', 'Not Approved'),
    ]

    full_name = models.CharField(max_length=200)
    age = models.PositiveIntegerField()
    height = models.CharField(max_length=20, help_text="e.g. 5'9\"")
    blood_group = models.CharField(max_length=10)
    phone_1 = models.CharField(max_length=20)
    phone_2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    place = models.CharField(max_length=255)
    education = models.CharField(max_length=255)
    aadhar_card_no = models.CharField(max_length=20)
    
    main_locality = models.CharField(max_length=50, choices=Staff.LOCALITY_CHOICES, blank=True, null=True, help_text="Major operational area")
    coat_size = models.CharField(max_length=5, choices=Staff.COAT_SIZE_CHOICES, blank=True, null=True)
    
    guardian_name = models.CharField(max_length=150)
    guardian_phone = models.CharField(max_length=20)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='unverified', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.get_status_display()})"


class PromotionRequest(models.Model):
    """Requests for staff promotion to the next level"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Not Approved'),
    ]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='promotion_requests')
    current_level = models.CharField(max_length=10)
    requested_level = models.CharField(max_length=10)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.staff.full_name}: {self.current_level} -> {self.requested_level} ({self.get_status_display()})"


class StaffNotice(models.Model):
    """Notice board messages from admin to all staff"""
    message = models.TextField()
    is_active = models.BooleanField(default=True, help_text="Show this notice on the staff portal front page")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"[{status}] Notice {self.id}"

