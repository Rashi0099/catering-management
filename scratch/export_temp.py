import os, sys, json, django

# Setup Django
sys.path.append('/home/rasheed/Documents/catrin_boys_website/catering_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from staff.models import Locality
from bookings.models import Client
from core.models import TermAndCondition, InvoiceItem

def decimal_default(obj):
    if hasattr(obj, '__float__'): return float(obj)
    return str(obj)

data = {
    'localities': list(Locality.objects.values('name')),
    'clients': list(Client.objects.values('name', 'phone')),
    'terms': list(TermAndCondition.objects.values('text', 'order')),
    'invoice_items': list(InvoiceItem.objects.values('name', 'default_price', 'order')),
}

with open('mastan_settings_sync.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, default=decimal_default, ensure_ascii=False)

print("Export successful: mastan_settings_sync.json")
