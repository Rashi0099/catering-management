# Catrin Boys Catering Website

This is the full Django-based web application for the Catrin Boys catering service. It features a public-facing website, a staff portal, and a comprehensive admin dashboard for managing bookings, staff, menu, and gallery.

## Features

- **Public Website:** Browsable menu, gallery, about us, contact, and event booking form.
- **Staff Portal (`/staff/login/`):** 
  - Personalized dashboard showing assigned bookings and upcoming events.
  - Ability to create new bookings and record client payments.
  - View personal earnings and payout history.
- **Admin Dashboard (`/admin-panel/`):**
  - Full control over all bookings and payments.
  - Comprehensive staff management including payout tracking and history.
  - Manage menu items and gallery images.
- **Database Administration (`/django-admin/`):** Raw database access for superusers.

## Tech Stack

- **Backend:** Django, Python 3.11+
- **Database:** PostgreSQL 15+
- **Frontend:** HTML, CSS, JavaScript (Vanilla design system)

## Local Development Setup

### Prerequisites
1. Install Python 3.11+
2. Install PostgreSQL 15+

### Database Setup
Open `psql` and run:
```sql
CREATE DATABASE catrinboys_db;
CREATE USER catrinboys_user WITH PASSWORD 'MyStrongPass123';
GRANT ALL PRIVILEGES ON DATABASE catrinboys_db TO catrinboys_user;
```

### Installation
1. Navigate to the project directory:
   ```bash
   cd catering_project
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Setup environment variables:
   Copy `.env.example` to `.env` and fill in the values (especially database credentials).
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```
7. Collect static files and start the server:
   ```bash
   python manage.py collectstatic --noinput
   python manage.py runserver
   ```
   
The app will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Deployment
This project is configured and recommended to be deployed on Railway.app. Check the `SETUP_GUIDE.txt` for detailed instructions on how to set up GitHub automatic deployments, domain configurations, and environment variables.

## Project Structure
- `core/`: Main app handling public pages.
- `menu/` & `gallery/`: Apps to manage and display catalog items.
- `bookings/`: Manages customer bookings, payment tracking, and testimonials.
- `staff/`: Custom authentications, staff management, attendance, and payouts.
- `templates/`: Global and app-level HTML templates.
- `scripts/`: Useful standalone test scripts for troubleshooting functionalities like Fast2SMS API.