from django.apps import AppConfig


class WorkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "work"
    verbose_name = "Suivi du travail"

    def ready(self) -> None:
        """Register cache invalidation hooks after the application is loaded."""
        from work import signals  # noqa: F401
