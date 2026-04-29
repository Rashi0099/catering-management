import os
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse


# URLs that must always work even in maintenance mode
ALWAYS_ALLOWED = [
    '/staff/login/',
    '/staff/logout/',
    '/django-admin/',
    '/static/',
    '/media/',
    '/firebase-messaging-sw.js',
    '/favicon.ico',
]


class MaintenanceMiddleware:
    """
    When MAINTENANCE_MODE=True in .env (or settings), every request from
    a non-staff/non-superuser visitor gets a 503 maintenance page.

    Logged-in staff and superusers see the real site as normal.
    The login page is always accessible so you can log in first.

    Toggle:
        In .env on the server → MAINTENANCE_MODE=True / False
        Then: sudo systemctl restart gunicorn
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Read from settings (set via .env)
        maintenance = getattr(settings, 'MAINTENANCE_MODE', False)

        if maintenance:
            path = request.path_info

            # Always allow these paths through
            for allowed in ALWAYS_ALLOWED:
                if path.startswith(allowed):
                    return self.get_response(request)

            # Allow logged-in staff / superusers through
            if hasattr(request, 'user') and request.user.is_authenticated:
                if request.user.is_staff or request.user.is_superuser:
                    return self.get_response(request)

            # Everyone else gets the maintenance page
            response = render(request, 'maintenance.html', status=503)
            response['Retry-After'] = '3600'
            return response

        return self.get_response(request)
