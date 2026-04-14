import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catering_site.settings")
django.setup()

from django.db.models import OuterRef, Subquery, Sum, DecimalField, Count, F
from django.db.models.functions import Coalesce
from staff.models import Staff, StaffPayout
from bookings.models import Booking

revenue_sq = Booking.objects.filter(
    assigned_to=OuterRef('pk'),
    status__in=['confirmed', 'completed']
).values('assigned_to').annotate(
    total=Sum('quoted_price')
).values('total')

paid_sq = StaffPayout.objects.filter(
    staff=OuterRef('pk'),
    status='paid'
).values('staff').annotate(
    total=Sum('amount')
).values('total')

pending_sq = StaffPayout.objects.filter(
    staff=OuterRef('pk'),
    status='pending'
).values('staff').annotate(
    total=Sum('amount')
).values('total')

qs = Staff.objects.annotate(
    annotated_revenue=Coalesce(Subquery(revenue_sq, output_field=DecimalField()), 0, output_field=DecimalField()),
    annotated_paid_out=Coalesce(Subquery(paid_sq, output_field=DecimalField()), 0, output_field=DecimalField()),
    annotated_pending_payout=Coalesce(Subquery(pending_sq, output_field=DecimalField()), 0, output_field=DecimalField())
).filter(is_active=True).order_by('full_name')

print("SQL:", qs.query)
staff_member = qs.first()
if staff_member:
    print("Testing Staff:", getattr(staff_member, 'annotated_revenue', 'N/A'), getattr(staff_member, 'annotated_paid_out', 'N/A'))
else:
    print("No staff")

