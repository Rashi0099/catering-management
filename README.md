# Mastan Catering & Services

A full-featured Django web application for **Mastan Catering & Services** — a professional catering business management platform with a public website, staff portal, admin dashboard, push notifications, and Android TWA apps.

**Live:** [https://mastan.in](https://mastan.in)

---

## Features

### 🌐 Public Website
- Browsable menu with categories and pricing
- Photo gallery with event showcases
- Event booking form with Terms & Conditions
- Contact page and About section

### 👨‍🍳 Staff Portal (`/staff/login/`)
- Personalized dashboard with assigned bookings and upcoming events
- Create bookings and record client payments
- View personal earnings, payout history, and attendance
- Profile management with photo upload and crop
- Push notification support (FCM via Firebase)

### 🛡️ Admin Dashboard (`/admin-panel/`)
- Full booking and payment management
- Staff management — add, promote, deactivate staff
- Payout tracking and payroll history
- Locality management for delivery zones
- Event reports with PDF export
- Notepad for internal notes
- Push notifications to all staff
- Settings dashboard

### 📱 Android Apps (TWA)
- Staff app and Admin app as Android Trusted Web Activities
- Native push notifications via Firebase Cloud Messaging (FCM)
- Installable from browser + distributable as APK

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.x, Python 3.11+ |
| Database | PostgreSQL 15+ |
| Frontend | HTML5, CSS3, Vanilla JS |
| Push Notifications | Firebase Cloud Messaging (FCM) |
| File Serving | WhiteNoise (static), Django (media) |
| PDF Export | WeasyPrint |
| Web Server | Gunicorn + Nginx (production) |
| Hosting | AWS EC2 |
| Android Apps | PWABuilder (TWA) |

---

## Project Structure

```
catering_project/
├── catering_site/          # Django project settings & URL config
├── core/                   # Public pages, admin views, utilities
├── bookings/               # Booking models, payment, testimonials
├── staff/                  # Custom auth, staff management, FCM, payouts
├── menu/                   # Menu categories and items
├── gallery/                # Gallery categories and images
├── templates/              # All HTML templates
│   ├── core/               # Base, public pages
│   ├── staff/              # Staff portal templates
│   ├── admin/              # Admin dashboard templates
│   ├── bookings/           # Booking flow templates
│   └── fcm_init.html       # Firebase push notification init (shared)
├── static/                 # Source static files (CSS, JS, icons)
│   ├── css/
│   ├── js/
│   └── icons/              # PWA icons (192x192, 512x512)
├── staticfiles/            # Collected static files (auto-generated, git-ignored)
├── media/                  # User-uploaded files (git-ignored)
├── scripts/
│   ├── server/             # Production server scripts
│   │   ├── deploy.sh           # Deploy: pull → migrate → collectstatic → restart
│   │   ├── setup.sh            # First-time server setup
│   │   ├── twa_patch.sh        # Staff TWA patch (run on server)
│   │   └── twa_admin_patch.sh  # Admin TWA patch (run on server)
│   └── debug/              # Dev/debug utilities (never run on production)
│       ├── list_users.py       # List all staff accounts
│       ├── populate_db.py      # Seed sample menu & gallery data
│       └── wipe_data.py        # ⚠️ Wipe all data (dev only!)
├── .env                    # Secret environment variables (git-ignored)
├── .env.example            # Template for .env
├── firebase-adminsdk.json  # Firebase service account (git-ignored)
├── private_key.pem         # VAPID private key (git-ignored)
├── public_key.pem          # VAPID public key (git-ignored)
├── manage.py
└── requirements.txt
```

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 15+

### 1. Database Setup
```sql
CREATE DATABASE catrinboys_db;
CREATE USER catrinboys_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE catrinboys_db TO catrinboys_user;
```

### 2. Clone & Install
```bash
cd catering_project
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
```bash
cp .env.example .env
# Edit .env and fill in your values
```

### 4. Migrate & Create Admin
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

The app is available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

| URL | Purpose |
|-----|---------|
| `/` | Public website |
| `/staff/login/` | Staff portal login |
| `/admin-panel/` | Admin dashboard |
| `/django-admin/` | Raw DB access (superusers only) |

---

## Production Deployment (AWS + Gunicorn + Nginx)

### First-time Setup
```bash
# On the server:
bash ~/catering_project/scripts/server/setup.sh
```

### Deploy Updates
```bash
bash ~/catering_project/scripts/server/deploy.sh
```

This script:
1. Pulls latest changes from `git`
2. Installs any new dependencies
3. Runs database migrations
4. Collects static files
5. Restarts Gunicorn

### Required Files on Server (NOT in git)
Place these files in `~/catering_project/` on the server:
- `.env` — environment variables
- `firebase-adminsdk.json` — Firebase Admin SDK credentials
- `private_key.pem` / `public_key.pem` — VAPID keys for Web Push

---

## Android TWA Apps

The Staff and Admin portals are packaged as Android Trusted Web Activity (TWA) apps for native push notification support.

### Build Staff App
```bash
# On the server:
bash ~/catering_project/scripts/server/twa_patch.sh
# Then visit https://www.pwabuilder.com → Enter: https://mastan.in/staff/
```

### Build Admin App
```bash
bash ~/catering_project/scripts/server/twa_admin_patch.sh
# Then visit https://www.pwabuilder.com → Enter: https://mastan.in/admin-panel/
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Django secret key (long random string) |
| `DEBUG` | ✅ | `False` in production |
| `ALLOWED_HOSTS` | ✅ | Comma-separated domains e.g. `mastan.in,www.mastan.in` |
| `DB_NAME` | ✅ | PostgreSQL database name |
| `DB_USER` | ✅ | PostgreSQL username |
| `DB_PASSWORD` | ✅ | PostgreSQL password |
| `DB_HOST` | ✅ | Database host (usually `localhost`) |
| `DB_PORT` | ✅ | Database port (usually `5432`) |
| `EMAIL_USER` | ✅ | Gmail address for sending emails |
| `EMAIL_PASS` | ✅ | Gmail App Password (not your real password) |

---

## Security

- HTTPS enforced in production with HSTS (1 year)
- CSRF protection on all forms and AJAX
- Login rate limiting (5 attempts → 5-minute lockout)
- Session hardening (HttpOnly, SameSite, 30-day expiry)
- File upload size limits (5 MB)
- No sensitive secrets in git (`.env`, `*.pem`, Firebase JSON are all git-ignored)