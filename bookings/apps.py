from django.apps import AppConfig

class BookingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bookings'

    def ready(self):
        # FIX: Import signals here so Django registers them exactly once.
        # This is the standard Django pattern to avoid double-registration.
        import bookings.signals  # noqa: F401
