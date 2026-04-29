#!/bin/bash
# ============================================
# Catrin Boys - Quick Setup Script
# ============================================

echo "🍽️  Setting up Catrin Boys Catering Website..."

# Install dependencies
pip install django pillow whitenoise

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (staff access for admin panel)
echo ""
echo "📋 Create your admin account:"
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput

echo ""
echo "✅ Setup complete!"
echo "▶  Run: python manage.py runserver"
echo "🌐 Website:    http://127.0.0.1:8000/"
echo "👑 Admin Panel: http://127.0.0.1:8000/admin-panel/"
echo "⚙️  Django Admin: http://127.0.0.1:8000/django-admin/"
