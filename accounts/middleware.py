"""Account security middleware."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect


class TemporaryPasswordChangeMiddleware:
    """Block business access until a temporary password is replaced."""

    allowed_paths = {
        "/api/v1/session/",
        "/api/v1/session/logout/",
        "/api/v1/session/password/",
        "/connexion/",
        "/deconnexion/",
    }

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        if not (
            user.is_authenticated and getattr(user, "password_change_required", False)
        ):
            return self.get_response(request)
        path = request.path
        if (
            path in self.allowed_paths
            or path.startswith("/app/")
            or path.startswith("/static/")
        ):
            return self.get_response(request)
        if path.startswith("/api/v1/"):
            return JsonResponse(
                {
                    "error": {
                        "code": "password_change_required",
                        "message": (
                            "Remplacez votre mot de passe temporaire avant de continuer."
                        ),
                        "fields": {},
                    }
                },
                status=403,
            )
        return redirect("react-app")
