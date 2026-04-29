#!/bin/bash
# Admin TWA Patch Script - Run this on AWS server
# Usage: bash ~/catering_project/twa_admin_patch.sh

set -e
cd ~/catering_project
echo "🚀 Applying Admin TWA patch..."

# ── 1. Create admin/manifest.json ────────────────────────────────────────────
echo "📄 Creating admin manifest..."
cat > templates/admin/manifest.json << 'MANIFEST'
{
  "name": "Mastan Admin",
  "short_name": "Admin",
  "description": "Mastan Catering Admin Management Application",
  "start_url": "/admin-panel/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#0d0f14",
  "theme_color": "#d4a852",
  "lang": "en",
  "gcm_sender_id": "227009036928",
  "prefer_related_applications": false,
  "categories": ["business", "management"],
  "icons": [
    {
      "src": "/static/icons/icon-192x192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/static/icons/icon-192x192_white.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "maskable"
    },
    {
      "src": "/static/icons/icon-512x512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
MANIFEST
echo "  ✅ manifest.json created"

# ── 2. Update core/admin_urls.py — add manifest route ─────────────────────────────
echo "🔗 Updating core/admin_urls.py..."
if ! grep -q "admin_manifest" core/admin_urls.py; then
  # Add imports at top if missing
  if ! grep -q "TemplateView" core/admin_urls.py; then
    sed -i '1s/^/from django.views.generic import TemplateView\nfrom django.views.decorators.cache import cache_control\n/' core/admin_urls.py
  fi
  
  # Add manifest route before closing ]
  sed -i "s|    path('api/invoice-items/',                     admin_views.api_get_invoice_items, name='admin_api_invoice_items'),|    path('api/invoice-items/',                     admin_views.api_get_invoice_items, name='admin_api_invoice_items'),\n    path('manifest.json', cache_control(no_cache=True, must_revalidate=True)(TemplateView.as_view(template_name='admin/manifest.json', content_type='application/json')), name='admin_manifest'),|" core/admin_urls.py
  echo "  ✅ admin_urls.py updated"
else
  echo "  ⏭️  admin_urls.py already patched, skipping"
fi

# ── 3. Update admin/custom_base.html — fix manifest link ────────────────────────────
echo "🔗 Updating admin/custom_base.html manifest link..."
if grep -q "url 'manifest.json'" templates/admin/custom_base.html; then
  python3 -c "
import re
with open('templates/admin/custom_base.html', 'r') as f:
    content = f.read()
content = re.sub(
    r'<link rel=\"manifest\" href=\"\{%[^%]*manifest\.json[^%]*%\}[^\"]*\">',
    '<link rel=\"manifest\" href=\"/admin-panel/manifest.json\">',
    content
)
with open('templates/admin/custom_base.html', 'w') as f:
    f.write(content)
"
  echo "  ✅ custom_base.html updated"
else
  echo "  ⏭️  custom_base.html already updated, skipping"
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
echo "✅ Admin TWA Patch Complete!"
echo ""
echo "Now go to: https://www.pwabuilder.com"
echo "Enter URL: https://mastan.in/admin-panel/"
echo "Generate the APK and upload it to the server just like you did for Staff."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
