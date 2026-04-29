"""
One-time seed script: populate Clients, InvoiceItems, Terms & Conditions, and Localities.
Run on server: python scripts/debug/seed_settings.py
"""
import os, sys, pathlib

# Auto-detect project root
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')

import django
django.setup()

from bookings.models import Client
from core.models import TermAndCondition, InvoiceItem
from staff.models import Locality

# ── 1. CLIENTS ────────────────────────────────────────────────────────────────
CLIENTS = [
    ("Flora events",        "9747373502"),
    ("Evora events",        "8086852689"),
    ("Paradise events",     "9526855683"),
    ("Tasty events",        "8606633442"),
    ("Sea star",            "9846317155"),
    ("Dost events",         "9846262465"),
    ("Vp events",           "9846494991"),
    ("Sweets",              "9633961799"),
    ("Saukarayam events",   "8086117069"),
    ("Food world",          "9605685288"),
    ("Elite events",        "9188230257"),
    ("Al Bakka",            "9048756630"),
    ("Apsara events",       ""),
    ("Safa events",         "9048756630"),
    ("Mastan events",       "8075645207"),
    ("Aura events",         "8281017942"),
    ("Madeena event",       "9947563104"),
]

created_c, skipped_c = 0, 0
for name, phone in CLIENTS:
    obj, created = Client.objects.get_or_create(name=name, defaults={'phone': phone})
    if created:
        created_c += 1
        print(f"  ✅ Client: {name}")
    else:
        skipped_c += 1
        print(f"  ⏭  Already exists: {name}")

print(f"\nClients → {created_c} added, {skipped_c} skipped\n")

# ── 2. INVOICE ITEMS ──────────────────────────────────────────────────────────
ITEMS = [
    ("Supervisor",      900,  1),
    ("Captain",         750,  2),
    ("Juice",           750,  3),
    ("Tea",             700,  4),
    ("Popcorn",         750,  5),
    ("Cotton candy",    700,  6),
    ("Hosting boys",    850,  7),
    ("Hosting girls",  1500,  8),
    ("Service girls",   750,  9),
    ("Boys",            600, 10),
    ("Travel expense",    0, 11),
    ("TA",                0, 12),
]

created_i, skipped_i = 0, 0
for name, price, order in ITEMS:
    obj, created = InvoiceItem.objects.get_or_create(
        name=name,
        defaults={'default_price': price, 'order': order}
    )
    if created:
        created_i += 1
        print(f"  ✅ Invoice item: {name} — ₹{price}")
    else:
        skipped_i += 1
        print(f"  ⏭  Already exists: {name}")

print(f"\nInvoice Items → {created_i} added, {skipped_i} skipped\n")

# ── 3. TERMS & CONDITIONS ─────────────────────────────────────────────────────
TERMS = [
    "ജോലി ചെയ്യുന്ന കമ്പനിയോട് വിശ്വസ്തതയും കൂറും പുലർത്തുന്നവർ ആയിരിക്കണം.",
    "വർക്ക് ബുക്ക് ചെയ്താൽ നിർബന്ധമായും സൈറ്റിൽ എത്തണം. \"ക്യാൻസലേഷൻ അനുവദിക്കുകയില്ല\".",
    "കൃത്യമായ സമയത്ത് സൈറ്റിൽ എത്തുകയും ക്യാപ്റ്റൻ/സീനിയേഴ്സ് പറഞ്ഞതനുസരിച്ച് വർക്ക് ചെയ്യുകയും ചെയ്താൽ താങ്കളിലുള്ള വിശ്വാസം വർദ്ധിപ്പിക്കാൻ അത് കാരണമാകും.",
    "അച്ചടക്കമുള്ള നല്ല സ്റ്റാഫുകളെ വാർത്തെടുക്കാൻ മൂല്യനിർണയം നടത്തും.",
    "വർക്കിന് പ്രവേശിച്ചാൽ പിന്നീടുള്ള സമയങ്ങളിൽ മൊബൈലുകൾക്ക് ഏർപ്പെടുത്തിയ നിയന്ത്രണത്തിന് താങ്കൾ പൂർണ്ണമായും സഹകരിക്കണം.",
    "റിപ്പോർട്ടിംഗ് മുതൽ ഡിസ്പോസൽ വരെ താങ്കളുടെ ഉത്തരവാദിത്വം കമ്പനിക്ക് ആയിരിക്കും.",
    "കമ്പനി ഏൽപ്പിച്ച ക്യാപ്റ്റൻ ആയിരിക്കും സൈറ്റിനെ പൂർണ ചുമതല — ക്യാപ്റ്റൻ തരുന്ന നിർദ്ദേശങ്ങൾ പാലിക്കാൻ താങ്കൾ ബാധ്യസ്ഥനാണ്.",
]

created_t, skipped_t = 0, 0
for i, text in enumerate(TERMS, start=1):
    obj, created = TermAndCondition.objects.get_or_create(text=text, defaults={'order': i})
    if created:
        created_t += 1
        print(f"  ✅ Term {i}: {text[:60]}...")
    else:
        skipped_t += 1
        print(f"  ⏭  Term already exists: {text[:60]}...")

print(f"\nTerms → {created_t} added, {skipped_t} skipped\n")

# ── 4. LOCALITIES ─────────────────────────────────────────────────────────────
LOCALITIES = [
    "Kondotti",
    "Areekode",
    "Kizhisseri",
    "Veluamburam",
    "Ramanattukara",
    "Farook",
    "Calicut",
    "Mavoor",
    "Manjeri",
]

created_l, skipped_l = 0, 0
for name in LOCALITIES:
    obj, created = Locality.objects.get_or_create(name=name)
    if created:
        created_l += 1
        print(f"  ✅ Locality: {name}")
    else:
        skipped_l += 1
        print(f"  ⏭  Already exists: {name}")

print(f"\nLocalities → {created_l} added, {skipped_l} skipped\n")
print("🎉 Seed complete!")
