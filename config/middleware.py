"""Project-specific HTTP middleware."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils import translation


class FrenchAdminLocaleMiddleware:
    """Render Django administration pages in French for every browser locale."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.path_info.startswith("/admin/"):
            return self.get_response(request)

        with translation.override("fr"):
            request.LANGUAGE_CODE = "fr"
            response = self.get_response(request)
        response.headers["Content-Language"] = "fr"
        return response
