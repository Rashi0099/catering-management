"""
core/middleware.py
──────────────────
Security middleware for the Catrin Boys catering platform.

LoginRateLimitMiddleware
  - Tracks failed login attempts per IP address using Django's cache backend.
  - After LOGIN_MAX_ATTEMPTS failures (default 5) within LOGIN_LOCKOUT_SECONDS
    (default 300s), the IP is locked out and receives an HTTP 429 response.
  - Successful login (redirect away from login page) clears the counter.
  - Works for BOTH the admin (/admin-panel/login/) and staff (/staff/login/) portals.
"""

from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings


class LoginRateLimitMiddleware:
    """Brute-force protection: lock out an IP after N failed login attempts."""

    LOGIN_PATHS = ['/staff/login/', '/admin-panel/login/']

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_attempts = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5)
        self.lockout_seconds = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 300)

    def __call__(self, request):
        if request.method == 'POST' and self._is_login_path(request.path):
            ip = self._get_client_ip(request)
            cache_key = f'login_fails_{ip}'
            attempts = cache.get(cache_key, 0)

            if attempts >= self.max_attempts:
                remaining = self.lockout_seconds
                return HttpResponse(
                    f'<html><body style="font-family:sans-serif;text-align:center;padding:60px;">'
                    f'<h2>Too many failed login attempts.</h2>'
                    f'<p>Your IP has been temporarily blocked for {self.lockout_seconds // 60} minutes.</p>'
                    f'<p>Please try again later.</p>'
                    f'</body></html>',
                    status=429,
                    content_type='text/html',
                )

        response = self.get_response(request)

        # Track failures: POST to login that did NOT redirect (meaning auth failed)
        if request.method == 'POST' and self._is_login_path(request.path):
            ip = self._get_client_ip(request)
            cache_key = f'login_fails_{ip}'

            if response.status_code == 200:
                # Still on the login page = failed attempt
                attempts = cache.get(cache_key, 0) + 1
                cache.set(cache_key, attempts, self.lockout_seconds)
            elif response.status_code in (301, 302, 303):
                # Successful login — clear the counter
                cache.delete(cache_key)

        return response

    def _is_login_path(self, path):
        return any(path.startswith(lp) for lp in self.LOGIN_PATHS)

    @staticmethod
    def _get_client_ip(request):
        """Get real IP, handling reverse proxies (nginx, Cloudflare, etc.)."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Take the first (leftmost) IP in the chain — that's the client
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')
