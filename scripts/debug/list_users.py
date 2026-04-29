"""
Debug Utility: List all staff users in the system.
Usage: python scripts/debug/list_users.py
"""
import os
import sys
import django

# Auto-detect project root (two levels up from this script)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from staff.models import Staff

print("=" * 60)
print("ALL USERS IN SYSTEM:")
print("=" * 60)
for u in Staff.objects.all().order_by('joined_at'):
    joined = u.joined_at.strftime('%Y-%m-%d') if u.joined_at else 'N/A'
    role = "SUPERUSER" if u.is_superuser else ("Staff" if u.is_staff else "User")
    print("  [%s] %s | %s | active=%s | joined=%s" % (u.id, u.username, role, u.is_active, joined))
print("=" * 60)
print("Total:", Staff.objects.count())
