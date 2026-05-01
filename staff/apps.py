from django.apps import AppConfig

class StaffConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'staff'

    def ready(self):
        # FIX: Import signals here so Django registers them exactly once.
        import staff.signals  # noqa: F401
