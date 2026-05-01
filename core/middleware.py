from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware

class SplitSessionMiddleware(SessionMiddleware):
    def process_request(self, request):
        # Determine the cookie name based on the URL path
        if request.path.startswith('/admin-panel/'):
            cookie_name = 'admin_sessionid'
        else:
            cookie_name = 'staff_sessionid'
            
        # Temporarily patch the request to use this cookie name
        session_key = request.COOKIES.get(cookie_name)
        request.session = self.SessionStore(session_key)

    def process_response(self, request, response):
        if request.path.startswith('/admin-panel/'):
            cookie_name = 'admin_sessionid'
        else:
            cookie_name = 'staff_sessionid'
            
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        if empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
        else:
            if accessed:
                request.session.save()
            if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                response.set_cookie(
                    cookie_name,
                    request.session.session_key, max_age=request.session.get_expiry_age(),
                    expires=request.session.get_expiry_date(),
                    domain=settings.SESSION_COOKIE_DOMAIN,
                    path=settings.SESSION_COOKIE_PATH,
                    secure=settings.SESSION_COOKIE_SECURE or None,
                    httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                    samesite=settings.SESSION_COOKIE_SAMESITE,
                )
        return response
