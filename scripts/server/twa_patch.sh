#!/bin/bash
# Mastan TWA Patch Script - Run this on AWS server
# Usage: bash ~/catering_project/twa_patch.sh

set -e
cd ~/catering_project
echo "🚀 Applying TWA patch..."

# ── 1. Create staff/manifest.json ────────────────────────────────────────────
echo "📄 Creating staff manifest..."
cat > templates/staff/manifest.json << 'MANIFEST'
{
  "name": "Mastan Staff",
  "short_name": "Mastan",
  "description": "Mastan Catering Staff Management Application",
  "start_url": "/staff/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#0b0f19",
  "theme_color": "#d4a852",
  "lang": "en",
  "gcm_sender_id": "227009036928",
  "prefer_related_applications": false,
  "categories": ["business", "productivity"],
  "icons": [
    {"src": "/static/icons/icon-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/static/icons/icon-192x192_white.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
    {"src": "/static/icons/icon-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
  ],
  "shortcuts": [
    {"name": "Dashboard", "short_name": "Dashboard", "url": "/staff/", "icons": [{"src": "/static/icons/icon-192x192.png", "sizes": "192x192"}]},
    {"name": "My Bookings", "short_name": "Bookings", "url": "/staff/bookings/", "icons": [{"src": "/static/icons/icon-192x192.png", "sizes": "192x192"}]}
  ]
}
MANIFEST
echo "  ✅ manifest.json created"

# ── 2. Update staff/urls.py — add manifest route ─────────────────────────────
echo "🔗 Updating staff/urls.py..."
# Only patch if not already patched
if ! grep -q "staff_manifest" staff/urls.py; then
  # Add imports at top if missing
  if ! grep -q "TemplateView" staff/urls.py; then
    sed -i '1s/^/from django.views.generic import TemplateView\nfrom django.views.decorators.cache import cache_control\n/' staff/urls.py
  fi
  # Add manifest route before closing ]
  sed -i "s|    path('save-fcm-token/', views.save_fcm_token, name='save_fcm_token'),|    path('save-fcm-token/', views.save_fcm_token, name='save_fcm_token'),\n    path('manifest.json', cache_control(no_cache=True, must_revalidate=True)(TemplateView.as_view(template_name='staff/manifest.json', content_type='application/json')), name='staff_manifest'),|" staff/urls.py
  echo "  ✅ urls.py updated"
else
  echo "  ⏭️  urls.py already patched, skipping"
fi

# ── 3. Update staff/base.html — fix manifest link ────────────────────────────
echo "🔗 Updating staff/base.html manifest link..."
if grep -q "url 'manifest.json'" templates/staff/base.html; then
  python3 -c "
import re
with open('templates/staff/base.html', 'r') as f:
    content = f.read()
content = re.sub(
    r'<link rel=\"manifest\" href=\"\{%[^%]*manifest\.json[^%]*%\}[^\"]*\">',
    '<link rel=\"manifest\" href=\"/staff/manifest.json\">',
    content
)
with open('templates/staff/base.html', 'w') as f:
    f.write(content)
"
  echo "  ✅ base.html updated"
else
  echo "  ⏭️  base.html already updated, skipping"
fi

# ── 4. Verify Django check passes ────────────────────────────────────────────
echo "🔍 Running Django check..."
source venv/bin/activate
python manage.py check --deploy 2>&1 | grep -E "WARNINGS|ERRORS|System check" || true
echo "  ✅ Check done"

# ── 5. Restart gunicorn ──────────────────────────────────────────────────────
echo "🔄 Restarting Gunicorn..."
sudo systemctl restart gunicorn
sleep 2
STATUS=$(sudo systemctl is-active gunicorn)
echo "  ✅ Gunicorn status: $STATUS"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ TWA Patch Complete!"
echo ""
echo "Verify these URLs:"
echo "  https://mastan.in/.well-known/assetlinks.json"
echo "  https://mastan.in/staff/manifest.json"
echo ""
echo "Then open PWABuilder: https://www.pwabuilder.com"
echo "Enter URL: https://mastan.in/staff/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
