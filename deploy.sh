#!/bin/bash
# Mastan's Catering Deployment Script

echo "🚀 Starting Deployment..."

# 1. Pull changes
echo "📥 Pulling latest changes from Git..."
git pull origin main

# 2. Activate venv
echo "📦 Activating Environment..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ venv not found! Creating a new one..."
    python3 -m venv venv
    source venv/bin/activate
fi

# 3. Install requirements
echo "⚙️ Installing dependencies..."
pip install -r requirements.txt

# 4. Run migrations
echo "🗄️ Running database migrations..."
python manage.py migrate

# 5. Collect static
echo "🎨 Collecting static files..."
python manage.py collectstatic --noinput

# 6. Restart Gunicorn
echo "🔄 Restarting Gunicorn Service..."
sudo systemctl restart gunicorn

echo "✅ Deployment Finished Successfully! Visit https://mastan.in"
