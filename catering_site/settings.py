from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if python-decouple is installed, otherwise use os.environ
try:
    from decouple import config, Csv
    def env(key, default=None, cast=None):
        if cast is not None:
            return config(key, default=default, cast=cast)
        return config(key, default=default)
    def env_list(key, default='*'):
        return config(key, default=default, cast=Csv())
except ImportError:
    def env(key, default=None, cast=None):
        val = os.environ.get(key, default)
        if cast and val is not None:
            return cast(val)
        return val
    def env_list(key, default='*'):
        val = os.environ.get(key, default)
        return [v.strip() for v in val.split(',')] if val else ['*']

SECRET_KEY        = env('SECRET_KEY', default='catrinboys-change-this-key-in-production-long-secure-string-1234')
DEBUG             = env('DEBUG', default='True') in (True, 'True', 'true', '1')
ALLOWED_HOSTS     = env_list('ALLOWED_HOSTS', default='*')
MAINTENANCE_MODE  = env('MAINTENANCE_MODE', default='False') in (True, 'True', 'true', '1')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Custom apps — staff MUST be first (custom AUTH_USER_MODEL)
    'staff.apps.StaffConfig',
    'core',
    'menu',
    'bookings.apps.BookingsConfig',
    'gallery',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # ── Maintenance mode — must be AFTER AuthenticationMiddleware ──
    'core.maintenance.MaintenanceMiddleware',
]

ROOT_URLCONF = 'catering_site.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'core.utils.pending_count_context',
            'core.context_processors.admin_pending_count',
        ],
    },
}]

# ── Custom User Model ────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'staff.Staff'

# ── Database — PostgreSQL ────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':       'django.db.backends.postgresql',
        'NAME':         env('DB_NAME',     default='catrinboys_db'),
        'USER':         env('DB_USER',     default='postgres'),
        'PASSWORD':     env('DB_PASSWORD', default='password'),
        'HOST':         env('DB_HOST',     default='localhost'),
        'PORT':         env('DB_PORT',     default='5432'),
        # Scalability: reuse DB connections instead of opening a new one every request
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 5,
        },
    }
}

# ── Cache ─────────────────────────────────────────────────────────────────────
# Used by pending_count_context, dashboard stats cache, and login rate limiter
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'catrinboys-cache',
        'TIMEOUT': 300,          # Default: 5 min
        'OPTIONS': {
            'MAX_ENTRIES': 1000, # Prevent unbounded memory growth
        }
    }
}

# ── Static & Media ───────────────────────────────────────────────────────────
STATIC_URL    = '/static/'
STATIC_ROOT   = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
else:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = env('EMAIL_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_PASS', default='')

# ── Auth ─────────────────────────────────────────────────────────────────────
LOGIN_URL          = '/staff/login/'
LOGIN_REDIRECT_URL = '/staff/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Security Headers (active in ALL environments) ────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True    # Prevent MIME-sniffing attacks
SECURE_BROWSER_XSS_FILTER   = True    # Legacy XSS filter header (IE compat)
X_FRAME_OPTIONS             = 'DENY'  # Prevent clickjacking globally
SECURE_REFERRER_POLICY      = 'strict-origin-when-cross-origin'

# ── Security Settings (production only — requires HTTPS) ─────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT            = True
    SECURE_PROXY_SSL_HEADER        = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_HSTS_SECONDS            = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True

# ── Session Hardening ────────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY    = True          # JS cannot read session cookie
SESSION_COOKIE_SAMESITE    = 'Lax'        # Block cross-site request riding
SESSION_COOKIE_NAME        = 'catrin_sess' # Obscure default 'sessionid' name
SESSION_COOKIE_AGE         = 60 * 60 * 24 * 30  # 30-day session — login once per month
SESSION_SAVE_EVERY_REQUEST = True          # Reset 30-day timer on every request (keeps active users logged in)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False   # Persist across browser restarts

# ── CSRF Hardening ───────────────────────────────────────────────────────────
CSRF_COOKIE_HTTPONLY = False      # Must remain False for AJAX compatibility
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_FAILURE_VIEW    = 'core.views.csrf_failure'

# ── Login Rate Limiting (used by core.middleware.LoginRateLimitMiddleware) ────
LOGIN_MAX_ATTEMPTS    = 5    # Attempts before lockout
LOGIN_LOCKOUT_SECONDS = 300  # 5-minute lockout window

# ── Password Validation ──────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 4},
    },
]

# ── File Upload Security ──────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB max POST body
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB max file upload


# ── Firebase Notifications ───────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials

cred_path = BASE_DIR / 'firebase-adminsdk.json'
if cred_path.exists() and not firebase_admin._apps:
    try:
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Error initializing Firebase Admin: {e}")
