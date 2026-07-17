from django.apps import AppConfig


class ApiConfig(AppConfig):
    """API application configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self) -> None:
        """Register OpenAPI extensions when Django loads the application."""
        from api import schema  # noqa: F401
